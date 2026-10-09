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

type Vertex = [f64; 3];

// ---------------------------------------------------------------------------
// Parsing
// ---------------------------------------------------------------------------

/// One SOLID / 3DFACE entity, with corners already in perimeter order.
#[derive(Clone, Copy)]
struct Quad {
    corners: [Vertex; 4],
    /// `true` when the entity is a triangle (4th corner missing or repeated).
    triangle: bool,
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

    fn finish(mut self) -> Quad {
        // A missing or repeated 4th corner means the entity is a triangle.
        let triangle = !self.has_fourth || self.corners[3] == self.corners[2];
        // SOLID stores the corners of a quad in "zig-zag" order (0, 1, 3, 2 around the
        // perimeter), whereas 3DFACE stores them in perimeter order.
        if self.kind == Kind::Solid && !triangle {
            self.corners.swap(2, 3);
        }
        Quad {
            corners: self.corners,
            triangle,
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

/// Merge the corners of all quads (vertices equal after rounding to `decimals`
/// places are shared) and triangulate them.
fn build_mesh(parts: &[Vec<Quad>], decimals: i32) -> Mesh {
    let scale = 10f64.powi(decimals);
    let n_quads: usize = parts.iter().map(Vec::len).sum();
    let mut index: FxHashMap<[i64; 3], i64> =
        FxHashMap::with_capacity_and_hasher(n_quads + n_quads / 4, Default::default());
    let mut points: Vec<f64> = Vec::with_capacity(n_quads * 3);
    let mut faces: Vec<i64> = Vec::with_capacity(n_quads * 6);

    for quad in parts.iter().flatten() {
        let n_corners = if quad.triangle { 3 } else { 4 };
        let mut ids = [0i64; 4];
        for (id, v) in ids.iter_mut().zip(&quad.corners).take(n_corners) {
            let key = [
                (v[0] * scale).round() as i64,
                (v[1] * scale).round() as i64,
                (v[2] * scale).round() as i64,
            ];
            let next = (points.len() / 3) as i64;
            *id = *index.entry(key).or_insert_with(|| {
                points.extend_from_slice(v);
                next
            });
        }
        let mut push = |a: i64, b: i64, c: i64| {
            // Skip degenerate triangles (repeated vertices).
            if a != b && b != c && a != c {
                faces.extend_from_slice(&[a, b, c]);
            }
        };
        push(ids[0], ids[1], ids[2]);
        if !quad.triangle {
            push(ids[0], ids[2], ids[3]);
        }
    }

    let n_points = points.len() / 3;
    let labels = connected_components(n_points, &faces);
    Mesh {
        points,
        faces,
        labels,
    }
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
    for tri in faces.chunks_exact(3) {
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

fn parse_dxf(data: &[u8], decimals: i32) -> Mesh {
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
    build_mesh(&parts, decimals)
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
    for (k, tri) in faces.chunks_exact(3).enumerate() {
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
    let mesh = py.detach(|| parse_dxf(data, decimals));
    into_arrays(py, mesh)
}

/// Parse a DXF file (read directly by Rust, without going through a Python string).
#[pyfunction]
#[pyo3(signature = (path, decimals = 6))]
fn parse_dxf_file<'py>(py: Python<'py>, path: PathBuf, decimals: i32) -> PyResult<MeshArrays<'py>> {
    let mesh = py.detach(|| -> io::Result<Mesh> {
        let data = std::fs::read(&path)?;
        Ok(parse_dxf(&data, decimals))
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

#[pymodule]
fn _dxf_io(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(parse_dxf_bytes, m)?)?;
    m.add_function(wrap_pyfunction!(parse_dxf_file, m)?)?;
    m.add_function(wrap_pyfunction!(write_dxf_string, m)?)?;
    m.add_function(wrap_pyfunction!(write_dxf_file, m)?)?;
    Ok(())
}
