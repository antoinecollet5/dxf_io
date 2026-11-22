"""Mesh attributes with dxf_io: attach point and cell data, export to PyVista.

Run with ``marimo edit examples/example_03_attributes.py``.
PyVista is optional: ``pip install "dxf_io[visualization]"``.
"""

import marimo

__generated_with = "0.25.2"
app = marimo.App()


@app.cell
def _():
    import tempfile
    from pathlib import Path

    import marimo as mo
    import numpy as np

    from dxf_io import MeshWithAttributes, dxf_to_manifold_meshes, write_dxf_fast

    try:
        import pyvista as pv
    except ImportError:
        pv = None
    return MeshWithAttributes, Path, dxf_to_manifold_meshes, mo, np, pv, tempfile, write_dxf_fast


@app.cell
def _(Path, np, tempfile, write_dxf_fast):
    # A demo file: two tetrahedra at different heights.
    tetra_points = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=float)
    tetra_faces = np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]])
    points = np.vstack([tetra_points, tetra_points + [3.0, 0.0, 2.0]])
    faces = np.vstack([tetra_faces, tetra_faces + 4])
    dxf_file = Path(tempfile.mkdtemp()) / "tetrahedra.dxf"
    write_dxf_fast(points, faces, dxf_file)
    return (dxf_file,)


@app.cell
def _(dxf_file, dxf_to_manifold_meshes, mo):
    parts = dxf_to_manifold_meshes(dxf_file, use_pyvista=False)
    component = mo.ui.slider(0, len(parts) - 1, value=0, label="Component")
    component
    return component, parts


@app.cell
def _(MeshWithAttributes, component, np, parts):
    part = parts[component.value]
    tri = part.points[part.faces]  # (n_faces, 3 corners, 3 coordinates)
    face_area = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    mesh = MeshWithAttributes(
        part.points,
        part.faces,
        point_data={"elevation": part.points[:, 2]},
        cell_data={"area": face_area},
    )
    return face_area, mesh


@app.cell
def _(component, face_area, mesh, mo):
    mo.md(
        f"""
        ## Component {component.value}

        - {mesh.n_points} points, {mesh.n_faces} triangles
        - Point data: {", ".join(mesh.point_data)}; cell data: {", ".join(mesh.cell_data)}
        - Total area: {face_area.sum():.3f}
        """
    )
    return


@app.cell
def _(mesh, mo, pv):
    if pv is None:
        output = mo.md("PyVista is not installed: `pip install 'dxf_io[visualization]'`.")
    else:
        poly = mesh.to_pyvista()
        output = mo.md(
            f"PyVista mesh: {poly.n_points} points, {poly.n_cells} cells, "
            f"arrays {list(poly.point_data)} + {list(poly.cell_data)}. "
            "Use `poly.plot(scalars='area')` to display it."
        )
    output
    return


if __name__ == "__main__":
    app.run()
