//! Fast SOLID / 3DFACE reader and writer for ASCII DXF files.
//!
//! The Python-facing API lives at the bottom of this file; everything above is plain
//! Rust so that it can be unit-tested without an interpreter.

use std::fs::File;
use std::io::{self, BufWriter, Write};
use std::path::PathBuf;

use ndarray::Array2;
use numpy::{IntoPyArray, PyArray1, PyArray2, PyReadonlyArray2, PyUntypedArrayMethods};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use rayon::prelude::*;
use rustc_hash::FxHashMap;
use std::hash::BuildHasher;
use std::sync::atomic::{AtomicU64, Ordering};

type Vertex = [f64; 3];

// ---------------------------------------------------------------------------
// Parsing
// ---------------------------------------------------------------------------

/// One SOLID / 3DFACE entity, with its corners in file order.
#[derive(Clone, Copy)]
struct Quad {
    corners: [Vertex; 4],
    /// `true` when the 4th corner is missing.
    triangle: bool,
    /// SOLID stores the corners of a quad in "zig-zag" order (0, 1, 3, 2 around the
    /// perimeter), whereas 3DFACE stores them in perimeter order.
    solid: bool,
}

#[derive(Clone, Copy, PartialEq)]
enum Kind {
    Solid,
    Face3d,
}

struct Entity {
    kind: Kind,
    corners: [Vertex; 4],
    has_fourth: bool,
}

impl Entity {
    fn new(kind: Kind) -> Self {
        Entity {
            kind,
            corners: [[0.0; 3]; 4],
            has_fourth: false,
        }
    }

    fn finish(self) -> Quad {
        // A 4th corner equal to the 3rd or the 1st (after vertex merging) also makes a
        // triangle: this is decided in `build_mesh`.
        Quad {
            corners: self.corners,
            triangle: !self.has_fourth,
            solid: self.kind == Kind::Solid,
        }
    }
}

/// Iterator over `(group code, value)` line pairs of an ASCII DXF buffer.
struct Pairs<'a> {
    data: &'a [u8],
    pos: usize,
}

#[inline]
fn trim(mut s: &[u8]) -> &[u8] {
    while let [first, rest @ ..] = s {
        if first.is_ascii_whitespace() {
            s = rest;
        } else {
            break;
        }
    }
    while let [rest @ .., last] = s {
        if last.is_ascii_whitespace() {
            s = rest;
        } else {
            break;
        }
    }
    s
}

impl<'a> Pairs<'a> {
    #[inline]
    fn line(&mut self) -> Option<&'a [u8]> {
        if self.pos >= self.data.len() {
            return None;
        }
        let rest = &self.data[self.pos..];
        let (line, advance) = match memchr::memchr(b'\n', rest) {
            Some(i) => (&rest[..i], i + 1),
            None => (rest, rest.len()),
        };
        self.pos += advance;
        Some(trim(line))
    }
}

impl<'a> Iterator for Pairs<'a> {
    type Item = (&'a [u8], &'a [u8]);

    #[inline]
    fn next(&mut self) -> Option<Self::Item> {
        let code = self.line()?;
        let value = self.line()?;
        Some((code, value))
    }
}

#[inline]
fn parse_code(code: &[u8]) -> Option<u32> {
    if code.is_empty() || code.len() > 5 {
        return None;
    }
    let mut n = 0u32;
    for &b in code {
        if !b.is_ascii_digit() {
            return None;
        }
        n = n * 10 + u32::from(b - b'0');
    }
    Some(n)
}

/// Parse every SOLID / 3DFACE entity of `data`, which must start on a group code line
/// and must not start in the middle of an entity.
fn parse_chunk(data: &[u8]) -> Vec<Quad> {
    // A quad takes roughly 150-250 bytes of text.
    let mut quads = Vec::with_capacity(data.len() / 200);
    let mut current: Option<Entity> = None;

    for (code, value) in (Pairs { data, pos: 0 }) {
        let Some(code) = parse_code(code) else {
            continue;
        };
        if code == 0 {
            if let Some(entity) = current.take() {
                quads.push(entity.finish());
            }
            current = match value {
                b"SOLID" => Some(Entity::new(Kind::Solid)),
                b"3DFACE" => Some(Entity::new(Kind::Face3d)),
                _ => None,
            };
            continue;
        }
        let Some(entity) = current.as_mut() else {
            continue;
        };
        // Group codes 10-13 / 20-23 / 30-33 are the x / y / z of corners 0-3.
        let (axis, corner) = match code {
            10..=13 => (0, (code - 10) as usize),
            20..=23 => (1, (code - 20) as usize),
            30..=33 => (2, (code - 30) as usize),
            _ => continue,
        };
        if let Ok(val) = fast_float2::parse::<f64, _>(value) {
            entity.corners[corner][axis] = val;
            if corner == 3 {
                entity.has_fourth = true;
            }
        }
    }
    if let Some(entity) = current.take() {
        quads.push(entity.finish());
    }
    quads
}

/// Split `data` in at most `n` chunks that each start on an entity boundary
/// (a `0` group code line), so that they can be parsed independently.
fn chunk_bounds(data: &[u8], n: usize) -> Vec<usize> {
    let mut bounds = vec![0];
    if n <= 1 {
        bounds.push(data.len());
        return bounds;
    }
    let mut lines_before = 0usize; // number of '\n' in data[..scanned]
    let mut scanned = 0usize;
    for k in 1..n {
        let target = data.len() / n * k;
        if target <= *bounds.last().unwrap() {
            continue;
        }
        // Count lines up to `target`, then move to the start of the next line.
        lines_before += memchr::memchr_iter(b'\n', &data[scanned..target]).count();
        let Some(i) = memchr::memchr(b'\n', &data[target..]) else {
            break;
        };
        let mut pos = target + i + 1;
        lines_before += 1;
        scanned = pos;
        // Group codes are on even lines: skip a value line if needed.
        if lines_before % 2 == 1 {
            let Some(i) = memchr::memchr(b'\n', &data[pos..]) else {
                break;
            };
            pos += i + 1;
            lines_before += 1;
            scanned = pos;
        }
        // Advance pair by pair to the next entity (group code 0).
        let mut pairs = Pairs { data, pos };
        loop {
            let start = pairs.pos;
            match pairs.next() {
                Some((code, _)) if parse_code(code) == Some(0) => {
                    pos = start;
                    break;
                }
                Some(_) => {}
                None => {
                    pos = data.len();
                    break;
                }
            }
        }
        if pos >= data.len() {
            break;
        }
        // Keep the line counter in sync with the new scan position.
        lines_before += memchr::memchr_iter(b'\n', &data[scanned..pos]).count();
        scanned = pos;
        if pos > *bounds.last().unwrap() {
            bounds.push(pos);
        }
    }
    bounds.push(data.len());
    bounds
}

/// Mesh produced by the parser, stored as flat row-major buffers.
struct Mesh {
    points: Vec<f64>,
    faces: Vec<i64>,
    labels: Vec<i64>,
}

/// Below this many quads, vertex merging runs on a single thread.
const PARALLEL_MERGE_MIN_QUADS: usize = 1 << 16;

/// Merge the corners of all quads (vertices equal after rounding to `decimals`
/// places are shared) and triangulate them.
///
/// Vertices are numbered by order of first appearance, whatever the number of threads.
/// Corners are distributed over `n_shards` hash maps by hash value; each shard is
/// filled by its own thread, then the shards are merged by first appearance.
fn build_mesh(quads: &[Quad], decimals: i32) -> Result<Mesh, String> {
    let n_corners = quads.len() * 4;
    if n_corners >= u32::MAX as usize {
        return Err(format!("too many entities ({})", quads.len()));
    }
    let scale = 10f64.powi(decimals);
    let hasher = rustc_hash::FxBuildHasher;
    let key_of = |v: &Vertex| -> [i64; 3] {
        [
            (v[0] * scale).round() as i64,
            (v[1] * scale).round() as i64,
            (v[2] * scale).round() as i64,
        ]
    };
    let n_shards = if quads.len() >= PARALLEL_MERGE_MIN_QUADS {
        rayon::current_num_threads().clamp(1, 64)
    } else {
        1
    };

    // `shard << 32 | shard-local vertex id` of every corner (unused for the 4th corner
    // of a triangle).
    let local_id: Vec<AtomicU64> = (0..n_corners).map(|_| AtomicU64::new(0)).collect();
    // For every shard, the first corner of each of its vertices (increasing).
    let firsts: Vec<Vec<u32>> = (0..n_shards)
        .into_par_iter()
        .map(|shard| {
            let mut index: FxHashMap<[i64; 3], u32> = FxHashMap::with_capacity_and_hasher(
                quads.len() / n_shards + quads.len() / (4 * n_shards),
                hasher,
            );
            let mut firsts = Vec::with_capacity(quads.len() / n_shards);
            for (q, quad) in quads.iter().enumerate() {
                let n = if quad.triangle { 3 } else { 4 };
                for (k, v) in quad.corners.iter().take(n).enumerate() {
                    let key = key_of(v);
                    if n_shards > 1 && (hasher.hash_one(key) >> 32) as usize % n_shards != shard {
                        continue;
                    }
                    let corner = (4 * q + k) as u32;
                    let next = firsts.len() as u32;
                    let id = *index.entry(key).or_insert_with(|| {
                        firsts.push(corner);
                        next
                    });
                    let packed = (shard as u64) << 32 | u64::from(id);
                    local_id[corner as usize].store(packed, Ordering::Relaxed);
                }
            }
            firsts
        })
        .collect();

    // Global vertex ids, by order of first appearance.
    let (global, first_corners): (Vec<Vec<u32>>, Vec<u32>) = if n_shards == 1 {
        // Single shard: local ids already are global ids.
        (Vec::new(), firsts.into_iter().next().unwrap_or_default())
    } else {
        let mut all: Vec<(u32, u32, u32)> = firsts
            .iter()
            .enumerate()
            .flat_map(|(s, f)| {
                f.iter()
                    .enumerate()
                    .map(move |(l, &c)| (c, s as u32, l as u32))
            })
            .collect();
        all.par_sort_unstable_by_key(|t| t.0);
        let mut global: Vec<Vec<u32>> = firsts.iter().map(|f| vec![0; f.len()]).collect();
        for (g, &(_, s, l)) in all.iter().enumerate() {
            global[s as usize][l as usize] = g as u32;
        }
        (global, all.into_iter().map(|t| t.0).collect())
    };

    let points: Vec<f64> = first_corners
        .par_iter()
        .flat_map_iter(|&c| quads[c as usize / 4].corners[c as usize % 4])
        .collect();

    // Triangulate in parallel, keeping the order of the entities.
    let vertex = |corner: usize| -> i64 {
        let packed = local_id[corner].load(Ordering::Relaxed);
        let id = packed & u64::from(u32::MAX);
        if n_shards == 1 {
            return id as i64;
        }
        i64::from(global[(packed >> 32) as usize][id as usize])
    };
    let faces: Vec<i64> = quads
        .par_iter()
        .enumerate()
        .with_min_len(4096)
        .flat_map_iter(|(q, quad)| {
            let n = if quad.triangle { 3 } else { 4 };
            let mut ids = [0i64; 4];
            for (k, id) in ids.iter_mut().enumerate().take(n) {
                *id = vertex(4 * q + k);
            }
            // Skip degenerate triangles (repeated vertices).
            let tri = |a: i64, b: i64, c: i64| (a != b && b != c && a != c).then_some([a, b, c]);
            let [a, b, c, d] = ids;
            // A 4th corner merged with the 3rd (DXF convention) or with the 1st (common
            // exporter shortcut) makes a triangle, for SOLID and 3DFACE alike.
            let (first, second) = if quad.triangle || d == c || d == a {
                (tri(a, b, c), None)
            } else if quad.solid {
                (tri(a, b, d), tri(a, d, c)) // perimeter a, b, d, c
            } else {
                (tri(a, b, c), tri(a, c, d)) // perimeter a, b, c, d
            };
            first.into_iter().chain(second).flatten()
        })
        .collect();

    let n_points = points.len() / 3;
    let labels = connected_components(n_points, &faces);
    Ok(Mesh {
        points,
        faces,
        labels,
    })
}

fn find(parent: &mut [u32], mut x: usize) -> usize {
    let mut root = x;
    while parent[root] as usize != root {
        root = parent[root] as usize;
    }
    // Path compression.
    while parent[x] as usize != root {
        let next = parent[x] as usize;
        parent[x] = root as u32;
        x = next;
    }
    root
}

/// Connected-component id of every point (ids are numbered by first appearance).
fn connected_components(n_points: usize, faces: &[i64]) -> Vec<i64> {
    let mut parent: Vec<u32> = (0..n_points as u32).collect();
    for tri in faces.as_chunks::<3>().0 {
        let a = find(&mut parent, tri[0] as usize);
        for &other in &tri[1..] {
            let b = find(&mut parent, other as usize);
            let a = find(&mut parent, a);
            if a != b {
                parent[b] = a as u32;
            }
        }
    }
    let mut ids = vec![-1i64; n_points];
    let mut labels = Vec::with_capacity(n_points);
    let mut next = 0i64;
    for i in 0..n_points {
        let root = find(&mut parent, i);
        if ids[root] < 0 {
            ids[root] = next;
            next += 1;
        }
        labels.push(ids[root]);
    }
    labels
}

fn parse_dxf(data: &[u8], decimals: i32) -> Result<Mesh, String> {
    // Chunks are only worth it for large inputs.
    let n_chunks = if data.len() > (4 << 20) {
        rayon::current_num_threads().max(1) * 4
    } else {
        1
    };
    let bounds = chunk_bounds(data, n_chunks);
    let parts: Vec<Vec<Quad>> = bounds
        .windows(2)
        .collect::<Vec<_>>()
        .into_par_iter()
        .map(|w| parse_chunk(&data[w[0]..w[1]]))
        .collect();
    let quads = if parts.len() == 1 {
        parts.into_iter().next().unwrap_or_default()
    } else {
        parts.concat()
    };
    build_mesh(&quads, decimals)
}

// ---------------------------------------------------------------------------
// Writing
// ---------------------------------------------------------------------------

const DXF_HEADER: &str = "  0\nSECTION\n  2\nHEADER\n  9\n$ACADVER\n  1\nAC1018\n  0\nENDSEC\n\
  0\nSECTION\n  2\nTABLES\n  0\nTABLE\n  2\nLAYER\n 70\n1\n\
  0\nLAYER\n  2\n0\n 70\n0\n 62\n7\n  6\nCONTINUOUS\n  0\nENDTAB\n\
  0\nENDSEC\n  0\nSECTION\n  2\nENTITIES\n";
const DXF_FOOTER: &str = "  0\nENDSEC\n  0\nEOF\n";

/// Append `v` with six decimals (like `format!("{:.6}", v)`, but much faster).
fn push_fixed6(buf: &mut Vec<u8>, v: f64) {
    if !v.is_finite() || v.abs() >= 1e12 {
        let _ = write!(buf, "{v:.6}");
        return;
    }
    let scaled = (v.abs() * 1e6).round() as u64;
    if v.is_sign_negative() && scaled != 0 {
        buf.push(b'-');
    }
    push_u64(buf, scaled / 1_000_000);
    buf.push(b'.');
    let frac = (scaled % 1_000_000) as u32;
    let mut digits = [b'0'; 6];
    let mut f = frac;
    for d in digits.iter_mut().rev() {
        *d = b'0' + (f % 10) as u8;
        f /= 10;
    }
    buf.extend_from_slice(&digits);
}

fn push_u64(buf: &mut Vec<u8>, mut n: u64) {
    let mut tmp = [0u8; 20];
    let mut i = tmp.len();
    loop {
        i -= 1;
        tmp[i] = b'0' + (n % 10) as u8;
        n /= 10;
        if n == 0 {
            break;
        }
    }
    buf.extend_from_slice(&tmp[i..]);
}

/// Render the 3DFACE entities of faces `first..first + faces.len() / 3`.
fn render_faces(points: &[f64], faces: &[i64], first: usize) -> Vec<u8> {
    let mut buf = Vec::with_capacity(faces.len() / 3 * 330);
    for (k, tri) in faces.as_chunks::<3>().0.iter().enumerate() {
        buf.extend_from_slice(b"  0\n3DFACE\n  8\n0\n 62\n");
        push_u64(&mut buf, ((first + k) % 255 + 1) as u64);
        buf.push(b'\n');
        // A 3DFACE always has four corners; a triangle repeats the third one.
        for corner in 0..4usize {
            let p = tri[corner.min(2)] as usize * 3;
            for (axis, base) in [10u64, 20, 30].into_iter().enumerate() {
                buf.push(b' ');
                push_u64(&mut buf, base + corner as u64);
                buf.push(b'\n');
                push_fixed6(&mut buf, points[p + axis]);
                buf.push(b'\n');
            }
        }
    }
    buf
}

fn check_faces(n_points: usize, faces: &[i64]) -> Result<(), String> {
    match faces.iter().find(|&&i| i < 0 || i as usize >= n_points) {
        Some(i) => Err(format!(
            "face index {i} is out of range for a mesh with {n_points} points"
        )),
        None => Ok(()),
    }
}

/// Write a complete DXF document to `sink`, formatting faces in parallel.
fn write_dxf<W: Write>(sink: &mut W, points: &[f64], faces: &[i64]) -> io::Result<()> {
    const BLOCK: usize = 16_384; // faces per parallel work item
    sink.write_all(DXF_HEADER.as_bytes())?;
    let batch = BLOCK * 3 * rayon::current_num_threads().max(1) * 4;
    let mut first = 0usize;
    for group in faces.chunks(batch) {
        let rendered: Vec<Vec<u8>> = group
            .par_chunks(BLOCK * 3)
            .enumerate()
            .map(|(i, chunk)| render_faces(points, chunk, first + i * BLOCK))
            .collect();
        for part in &rendered {
            sink.write_all(part)?;
        }
        first += group.len() / 3;
    }
    sink.write_all(DXF_FOOTER.as_bytes())
}

// ---------------------------------------------------------------------------
// Python API
// ---------------------------------------------------------------------------

type MeshArrays<'py> = (
    Bound<'py, PyArray2<f64>>,
    Bound<'py, PyArray2<i64>>,
    Bound<'py, PyArray1<i64>>,
);

fn into_arrays<'py>(py: Python<'py>, mesh: Mesh) -> PyResult<MeshArrays<'py>> {
    let n_points = mesh.points.len() / 3;
    let n_faces = mesh.faces.len() / 3;
    let points = Array2::from_shape_vec((n_points, 3), mesh.points)
        .map_err(|e| PyValueError::new_err(e.to_string()))?;
    let faces = Array2::from_shape_vec((n_faces, 3), mesh.faces)
        .map_err(|e| PyValueError::new_err(e.to_string()))?;
    Ok((
        points.into_pyarray(py),
        faces.into_pyarray(py),
        PyArray1::from_vec(py, mesh.labels),
    ))
}

/// Parse DXF content given as bytes.
///
/// Returns ``(points, faces, labels)``: float64 ``(N, 3)`` coordinates, int64
/// ``(M, 3)`` triangle indices and the int64 connected-component id of each point.
#[pyfunction]
#[pyo3(signature = (data, decimals = 6))]
fn parse_dxf_bytes<'py>(py: Python<'py>, data: &[u8], decimals: i32) -> PyResult<MeshArrays<'py>> {
    let mesh = py
        .detach(|| parse_dxf(data, decimals))
        .map_err(PyValueError::new_err)?;
    into_arrays(py, mesh)
}

/// Parse a DXF file (read directly by Rust, without going through a Python string).
#[pyfunction]
#[pyo3(signature = (path, decimals = 6))]
fn parse_dxf_file<'py>(py: Python<'py>, path: PathBuf, decimals: i32) -> PyResult<MeshArrays<'py>> {
    let mesh = py.detach(|| -> PyResult<Mesh> {
        let data = std::fs::read(&path)?;
        parse_dxf(&data, decimals).map_err(PyValueError::new_err)
    })?;
    into_arrays(py, mesh)
}

fn views<'a>(
    points: &'a PyReadonlyArray2<'_, f64>,
    faces: &'a PyReadonlyArray2<'_, i64>,
) -> PyResult<(&'a [f64], &'a [i64])> {
    if points.shape()[1] != 3 || faces.shape()[1] != 3 {
        return Err(PyValueError::new_err(
            "points and faces must have shape (N, 3)",
        ));
    }
    let pts = points
        .as_slice()
        .map_err(|_| PyValueError::new_err("points must be C-contiguous"))?;
    let fcs = faces
        .as_slice()
        .map_err(|_| PyValueError::new_err("faces must be C-contiguous"))?;
    check_faces(pts.len() / 3, fcs).map_err(PyValueError::new_err)?;
    Ok((pts, fcs))
}

/// Render a triangle mesh as a DXF document made of 3DFACE entities.
#[pyfunction]
fn write_dxf_string(
    py: Python<'_>,
    points: PyReadonlyArray2<'_, f64>,
    faces: PyReadonlyArray2<'_, i64>,
) -> PyResult<String> {
    let (pts, fcs) = views(&points, &faces)?;
    let bytes = py.detach(|| -> io::Result<Vec<u8>> {
        let mut out = Vec::with_capacity(fcs.len() / 3 * 330 + 512);
        write_dxf(&mut out, pts, fcs)?;
        Ok(out)
    })?;
    String::from_utf8(bytes).map_err(|e| PyValueError::new_err(e.to_string()))
}

/// Write a triangle mesh to ``path`` as a DXF document made of 3DFACE entities.
#[pyfunction]
fn write_dxf_file(
    py: Python<'_>,
    path: PathBuf,
    points: PyReadonlyArray2<'_, f64>,
    faces: PyReadonlyArray2<'_, i64>,
) -> PyResult<()> {
    let (pts, fcs) = views(&points, &faces)?;
    py.detach(|| -> io::Result<()> {
        let mut out = BufWriter::with_capacity(1 << 20, File::create(&path)?);
        write_dxf(&mut out, pts, fcs)?;
        out.flush()
    })?;
    Ok(())
}

/// The module holds no global state, so it is safe on free-threaded Python builds.
#[pymodule(gil_used = false)]
fn _dxf_io(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(parse_dxf_bytes, m)?)?;
    m.add_function(wrap_pyfunction!(parse_dxf_file, m)?)?;
    m.add_function(wrap_pyfunction!(write_dxf_string, m)?)?;
    m.add_function(wrap_pyfunction!(write_dxf_file, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn face(corners: &[[f64; 3]]) -> String {
        let mut out = String::from("  0\n3DFACE\n  8\n0\n");
        for (i, c) in corners.iter().enumerate() {
            for (axis, v) in c.iter().enumerate() {
                out += &format!(" {}\n{}\n", 10 * (axis + 1) + i, v);
            }
        }
        out
    }

    fn grid(n: usize) -> String {
        let mut out = String::from("  0\nSECTION\n  2\nENTITIES\n");
        for i in 0..n {
            for j in 0..n {
                let (x, y) = (i as f64, j as f64);
                out += &face(&[
                    [x, y, 0.0],
                    [x + 1.0, y, 0.0],
                    [x + 1.0, y + 1.0, 0.0],
                    [x, y + 1.0, 0.0],
                ]);
            }
        }
        out + "  0\nENDSEC\n  0\nEOF\n"
    }

    #[test]
    fn fixed6_matches_std_format() {
        for v in [
            0.0,
            -0.0,
            1.5,
            -0.5,
            1234.5678915,
            1e-9,
            -1e-9,
            999_999.999_999_7,
        ] {
            let mut buf = Vec::new();
            push_fixed6(&mut buf, v);
            let expected = format!("{:.6}", v).replace("-0.000000", "0.000000");
            assert_eq!(String::from_utf8(buf).unwrap(), expected, "value {v}");
        }
    }

    #[test]
    fn chunked_parse_equals_single_chunk() {
        let text = grid(60);
        let data = text.as_bytes();
        let single = parse_chunk(data);
        for n in [2, 3, 7, 16, 64] {
            let bounds = chunk_bounds(data, n);
            assert!(bounds.windows(2).all(|w| w[0] < w[1]));
            let chunked: Vec<Quad> = bounds
                .windows(2)
                .flat_map(|w| parse_chunk(&data[w[0]..w[1]]))
                .collect();
            assert_eq!(chunked.len(), single.len(), "{n} chunks");
            for (a, b) in chunked.iter().zip(&single) {
                assert_eq!(a.corners, b.corners);
                assert_eq!(a.triangle, b.triangle);
            }
        }
    }

    #[test]
    fn sharded_merge_equals_single_shard() {
        // Above PARALLEL_MERGE_MIN_QUADS, merging is sharded: the result must not change.
        let quads = parse_chunk(grid(300).as_bytes());
        assert!(quads.len() >= PARALLEL_MERGE_MIN_QUADS);
        let sharded = build_mesh(&quads, 6).unwrap();
        let pool = rayon::ThreadPoolBuilder::new()
            .num_threads(1)
            .build()
            .unwrap();
        let serial = pool.install(|| build_mesh(&quads, 6)).unwrap();
        assert_eq!(sharded.points, serial.points);
        assert_eq!(sharded.faces, serial.faces);
        assert_eq!(sharded.labels, serial.labels);
        assert_eq!(serial.points.len() / 3, 301 * 301);
        assert_eq!(serial.faces.len() / 3, 2 * 300 * 300);
        assert!(serial.labels.iter().all(|&l| l == 0));
    }

    #[test]
    fn write_then_parse_roundtrip() {
        let points = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 5.0, 5.0, 5.0];
        let faces = [0, 1, 2, 1, 2, 3];
        let mut out = Vec::new();
        write_dxf(&mut out, &points, &faces).unwrap();
        let mesh = parse_dxf(&out, 6).unwrap();
        assert_eq!(mesh.points, points);
        assert_eq!(mesh.faces, faces);
        assert!(check_faces(4, &[0, 1, 4]).is_err());
    }
}
