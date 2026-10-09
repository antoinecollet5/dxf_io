use ndarray::{Array1, Array2};
use numpy::{IntoPyArray, PyArray1, PyArray2};
use pyo3::prelude::*;
use rustc_hash::FxHashMap;

type Vertex = [f64; 3];

/// Entity currently being read from the DXF stream.
#[derive(Clone, Copy, PartialEq)]
enum Kind {
    Solid,
    Face3d,
}

/// Accumulates the (up to) four corners of a SOLID / 3DFACE entity.
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

    /// Triangles (as corner indices) describing the entity.
    ///
    /// For SOLID the corners are stored in "zig-zag" order (0, 1, 3, 2 around the
    /// perimeter), whereas 3DFACE stores them in perimeter order.
    fn triangles(&self) -> Vec<[usize; 3]> {
        let perimeter: [usize; 4] = match self.kind {
            Kind::Solid => [0, 1, 3, 2],
            Kind::Face3d => [0, 1, 2, 3],
        };
        let c = &self.corners;
        // A missing or repeated 4th corner means the entity is a triangle.
        if !self.has_fourth || c[3] == c[2] {
            return vec![[0, 1, 2]];
        }
        let [a, b, cc, d] = perimeter;
        vec![[a, b, cc], [a, cc, d]]
    }
}

struct Builder {
    points: Vec<Vertex>,
    faces: Vec<[usize; 3]>,
    index: FxHashMap<[i64; 3], usize>,
    scale: f64,
}

impl Builder {
    fn new(decimals: i32) -> Self {
        Builder {
            points: Vec::new(),
            faces: Vec::new(),
            index: FxHashMap::default(),
            scale: 10f64.powi(decimals),
        }
    }

    fn vertex_id(&mut self, v: Vertex) -> usize {
        let key = [
            (v[0] * self.scale).round() as i64,
            (v[1] * self.scale).round() as i64,
            (v[2] * self.scale).round() as i64,
        ];
        if let Some(&idx) = self.index.get(&key) {
            return idx;
        }
        let idx = self.points.len();
        self.points.push(v);
        self.index.insert(key, idx);
        idx
    }

    fn push_entity(&mut self, entity: &Entity) {
        for tri in entity.triangles() {
            let ids = [
                self.vertex_id(entity.corners[tri[0]]),
                self.vertex_id(entity.corners[tri[1]]),
                self.vertex_id(entity.corners[tri[2]]),
            ];
            // Skip degenerate triangles (repeated vertices).
            if ids[0] != ids[1] && ids[1] != ids[2] && ids[0] != ids[2] {
                self.faces.push(ids);
            }
        }
    }
}

/// Parse SOLID and 3DFACE entities from ASCII DXF content.
///
/// Vertices are merged when they are equal after rounding to `decimals` places.
fn parse_dxf(content: &str, decimals: i32) -> (Vec<Vertex>, Vec<[usize; 3]>) {
    let mut builder = Builder::new(decimals);
    let mut current: Option<Entity> = None;
    let mut lines = content.lines();

    while let (Some(code_line), Some(value_line)) = (lines.next(), lines.next()) {
        let Ok(code) = code_line.trim().parse::<i32>() else {
            continue;
        };
        let value = value_line.trim();

        if code == 0 {
            if let Some(entity) = current.take() {
                builder.push_entity(&entity);
            }
            current = match value {
                "SOLID" => Some(Entity::new(Kind::Solid)),
                "3DFACE" => Some(Entity::new(Kind::Face3d)),
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
        if let Ok(val) = value.parse::<f64>() {
            entity.corners[corner][axis] = val;
            if corner == 3 {
                entity.has_fourth = true;
            }
        }
    }
    if let Some(entity) = current.take() {
        builder.push_entity(&entity);
    }

    (builder.points, builder.faces)
}

struct UnionFind {
    parent: Vec<usize>,
    rank: Vec<u32>,
}

impl UnionFind {
    fn new(n: usize) -> Self {
        UnionFind {
            parent: (0..n).collect(),
            rank: vec![0; n],
        }
    }

    fn find(&mut self, x: usize) -> usize {
        if self.parent[x] != x {
            self.parent[x] = self.find(self.parent[x]);
        }
        self.parent[x]
    }

    fn union(&mut self, x: usize, y: usize) {
        let px = self.find(x);
        let py = self.find(y);
        if px != py {
            if self.rank[px] < self.rank[py] {
                self.parent[px] = py;
            } else if self.rank[px] > self.rank[py] {
                self.parent[py] = px;
            } else {
                self.parent[py] = px;
                self.rank[px] += 1;
            }
        }
    }
}

fn extract_components(n_points: usize, faces: &[[usize; 3]]) -> Vec<usize> {
    if n_points == 0 {
        return Vec::new();
    }
    let max_vertex = n_points - 1;
    let mut uf = UnionFind::new(n_points);

    for &face in faces {
        uf.union(face[0], face[1]);
        uf.union(face[1], face[2]);
    }

    let mut labels = vec![0; max_vertex + 1];
    let mut component_id = 0;
    let mut next_id = FxHashMap::default();

    for i in 0..=max_vertex {
        let root = uf.find(i);
        if !next_id.contains_key(&root) {
            next_id.insert(root, component_id);
            component_id += 1;
        }
        labels[i] = next_id[&root];
    }

    labels
}

fn write_dxf_face(vertices: &[Vertex; 3], face_id: usize) -> String {
    let mut dxf_data = String::new();
    dxf_data.push_str("  0\n3DFACE\n");
    dxf_data.push_str("  8\n0\n");
    dxf_data.push_str(&format!(" 62\n{}\n", face_id % 255 + 1));

    // A 3DFACE always has four corners; a triangle repeats the third one.
    for i in 0..4 {
        let v = vertices[i.min(2)];
        dxf_data.push_str(&format!(" {}\n{:.6}\n", 10 + i, v[0]));
        dxf_data.push_str(&format!(" {}\n{:.6}\n", 20 + i, v[1]));
        dxf_data.push_str(&format!(" {}\n{:.6}\n", 30 + i, v[2]));
    }

    dxf_data
}

fn write_dxf(points: &[[f64; 3]], faces: &[[usize; 3]]) -> String {
    let mut dxf_content = String::new();

    dxf_content.push_str("  0\nSECTION\n  2\nHEADER\n  9\n$ACADVER\n  1\nAC1018\n  0\nENDSEC\n");
    dxf_content.push_str("  0\nSECTION\n  2\nTABLES\n  0\nTABLE\n  2\nLAYER\n 70\n1\n");
    dxf_content.push_str("  0\nLAYER\n  2\n0\n 70\n0\n 62\n7\n  6\nCONTINUOUS\n  0\nENDTAB\n");
    dxf_content.push_str("  0\nENDSEC\n  0\nSECTION\n  2\nENTITIES\n");

    for (face_idx, face) in faces.iter().enumerate() {
        let vertices = [
            points[face[0]],
            points[face[1]],
            points[face[2]],
        ];
        dxf_content.push_str(&write_dxf_face(&vertices, face_idx));
    }

    dxf_content.push_str("  0\nENDSEC\n  0\nEOF\n");
    dxf_content
}

#[pyclass]
struct RawMesh {
    #[pyo3(get)]
    points: Vec<[f64; 3]>,
    #[pyo3(get)]
    faces: Vec<[usize; 3]>,
    #[pyo3(get)]
    labels: Vec<usize>,
}

#[pymethods]
impl RawMesh {
    #[new]
    fn new(points: Vec<[f64; 3]>, faces: Vec<[usize; 3]>, labels: Vec<usize>) -> Self {
        RawMesh {
            points,
            faces,
            labels,
        }
    }

    #[getter]
    fn n_points(&self) -> usize {
        self.points.len()
    }

    #[getter]
    fn n_faces(&self) -> usize {
        self.faces.len()
    }

    #[getter]
    fn n_components(&self) -> usize {
        self.labels.iter().max().map_or(0, |m| m + 1)
    }

    fn points_array<'py>(&self, py: Python<'py>) -> Bound<'py, PyArray2<f64>> {
        let points_2d = Array2::from_shape_vec(
            (self.points.len(), 3),
            self.points.iter().flat_map(|p| vec![p[0], p[1], p[2]]).collect(),
        )
        .unwrap();
        points_2d.into_pyarray(py)
    }

    fn faces_array<'py>(&self, py: Python<'py>) -> Bound<'py, PyArray2<usize>> {
        let faces_2d = Array2::from_shape_vec(
            (self.faces.len(), 3),
            self.faces.iter().flat_map(|f| vec![f[0], f[1], f[2]]).collect(),
        )
        .unwrap();
        faces_2d.into_pyarray(py)
    }

    fn labels_array<'py>(&self, py: Python<'py>) -> Bound<'py, PyArray1<usize>> {
        Array1::from_vec(self.labels.clone()).into_pyarray(py)
    }

    fn to_dxf(&self) -> String {
        write_dxf(&self.points, &self.faces)
    }
}

#[pyfunction]
#[pyo3(signature = (dxf_content, decimals = 6))]
fn parse_dxf_fast(dxf_content: &str, decimals: i32) -> PyResult<RawMesh> {
    let (points, faces) = parse_dxf(dxf_content, decimals);
    let labels = extract_components(points.len(), &faces);

    Ok(RawMesh {
        points,
        faces,
        labels,
    })
}

#[pyfunction]
fn write_dxf_fast(points: Vec<[f64; 3]>, faces: Vec<[usize; 3]>) -> PyResult<String> {
    Ok(write_dxf(&points, &faces))
}

#[pymodule]
fn _dxf_io(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(parse_dxf_fast, m)?)?;
    m.add_function(wrap_pyfunction!(write_dxf_fast, m)?)?;
    m.add_class::<RawMesh>()?;
    Ok(())
}
