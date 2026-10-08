use ndarray::{Array1, Array2};
use numpy::{IntoPyArray, PyArray1, PyArray2};
use pyo3::prelude::*;
use rustc_hash::FxHashMap;

const TOLERANCE: f64 = 1e-9;

#[inline]
fn is_close(a: &[f64; 3], b: &[f64; 3], tol: f64) -> bool {
    (a[0] - b[0]).abs() < tol && (a[1] - b[1]).abs() < tol && (a[2] - b[2]).abs() < tol
}

#[inline]
fn float_to_bits(f: f64) -> u64 {
    f.to_bits()
}

fn parse_dxf(content: &str) -> (Vec<[f64; 3]>, Vec<[usize; 3]>) {
    let mut points = Vec::new();
    let mut faces = Vec::new();
    let mut vertices = Vec::new();
    let mut in_solid = false;
    let mut lines = content.lines().peekable();

    while let Some(line) = lines.next() {
        match line.trim() {
            "SOLID" => in_solid = true,
            "ENDSOL" => {
                in_solid = false;
                if !vertices.is_empty() {
                    let is_triangle = is_close(&vertices[3], &vertices[2], TOLERANCE)
                        || is_close(&vertices[3], &vertices[0], TOLERANCE);

                    if vertices.len() >= 3 {
                        for i in 0..(if is_triangle { 3 } else { 4 }) {
                            let mut found = false;
                            for (j, &existing) in points.iter().enumerate() {
                                if is_close(&vertices[i], &existing, TOLERANCE) {
                                    vertices[i] = existing;
                                    faces.push(j);
                                    found = true;
                                    break;
                                }
                            }
                            if !found {
                                points.push(vertices[i]);
                                faces.push(points.len() - 1);
                            }
                        }
                    }
                    vertices.clear();
                }
            }
            code if in_solid => {
                if let Ok(code_num) = code.parse::<usize>() {
                    if code_num == 10 || code_num == 20 || code_num == 30 {
                        if let Some(val_line) = lines.next() {
                            if let Ok(val) = val_line.trim().parse::<f64>() {
                                match code_num {
                                    10 => vertices.push([val, 0.0, 0.0]),
                                    20 => {
                                        if !vertices.is_empty() {
                                            vertices.last_mut().unwrap()[1] = val;
                                        }
                                    }
                                    30 => {
                                        if !vertices.is_empty() {
                                            vertices.last_mut().unwrap()[2] = val;
                                        }
                                    }
                                    _ => {}
                                }
                            }
                        }
                    }
                }
            }
            _ => {}
        }
    }

    let faces_vec: Vec<[usize; 3]> = faces
        .chunks_exact(3)
        .map(|chunk| [chunk[0], chunk[1], chunk[2]])
        .collect();

    (points, faces_vec)
}

fn deduplicate_points(
    points: &[[f64; 3]],
    faces: &[[usize; 3]],
) -> (Vec<[f64; 3]>, Vec<[usize; 3]>) {
    let mut unique_points = Vec::new();
    let mut point_map = FxHashMap::default();
    let mut new_faces = Vec::new();

    for &vertex_idx_array in faces {
        let mut face_indices = [0, 0, 0];
        for (i, &vertex_idx) in vertex_idx_array.iter().enumerate() {
            if (vertex_idx as usize) < points.len() {
                let point = points[vertex_idx as usize];
                let bits = float_to_bits(point[0]) ^ float_to_bits(point[1]) ^ float_to_bits(point[2]);

                let new_idx = if let Some(&idx) = point_map.get(&bits) {
                    idx
                } else {
                    unique_points.push(point);
                    let idx = unique_points.len() - 1;
                    point_map.insert(bits, idx);
                    idx
                };

                face_indices[i] = new_idx;
            }
        }
        new_faces.push(face_indices);
    }

    (unique_points, new_faces)
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

fn extract_components(faces: &[[usize; 3]]) -> Vec<usize> {
    let max_vertex = faces.iter().flat_map(|f| f.iter()).max().copied().unwrap_or(0);
    let mut uf = UnionFind::new(max_vertex + 1);

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

fn write_dxf_face(vertices: &[[f64; 3]; 3], face_id: usize) -> String {
    let mut dxf_data = String::new();
    dxf_data.push_str("  0\n3DFACE\n");
    dxf_data.push_str("  8\n0\n");
    dxf_data.push_str(&format!(" 62\n{}\n", face_id % 255 + 1));

    // Write all three vertices of the triangle
    for i in 0..3 {
        let code = 10 + i * 10;
        dxf_data.push_str(&format!(" {}\n{:.6}\n", code, vertices[i][0]));
        dxf_data.push_str(&format!(" {}\n{:.6}\n", code + 20, vertices[i][1]));
        dxf_data.push_str(&format!(" {}\n{:.6}\n", code + 30, vertices[i][2]));
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
        self.labels.iter().max().copied().unwrap_or(0) + 1
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
fn parse_dxf_fast(dxf_content: &str) -> PyResult<RawMesh> {
    let (points, faces) = parse_dxf(dxf_content);
    let (dedup_points, dedup_faces) = deduplicate_points(&points, &faces);
    let labels = extract_components(&dedup_faces);

    Ok(RawMesh {
        points: dedup_points,
        faces: dedup_faces,
        labels,
    })
}

#[pyfunction]
fn write_dxf_fast(points: Vec<[f64; 3]>, faces: Vec<[usize; 3]>) -> PyResult<String> {
    Ok(write_dxf(&points, &faces))
}

#[pymodule]
fn dxf_io(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(parse_dxf_fast, m)?)?;
    m.add_function(wrap_pyfunction!(write_dxf_fast, m)?)?;
    m.add_class::<RawMesh>()?;
    Ok(())
}
