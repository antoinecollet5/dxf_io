"""Basic DXF parsing with dxf_io: parse a file, split it into parts, inspect them.

Run with ``marimo edit examples/example_01_basic_parsing.py``.
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

    from dxf_io import diagnose_mesh, dxf_to_manifold_meshes, parse_dxf_fast, write_dxf_fast

    return (
        Path,
        diagnose_mesh,
        dxf_to_manifold_meshes,
        mo,
        np,
        parse_dxf_fast,
        tempfile,
        write_dxf_fast,
    )


@app.cell
def _(Path, np, tempfile, write_dxf_fast):
    # A demo file: three disjoint unit cubes made of triangles.
    cube_points = np.array([[x, y, z] for z in (0, 1) for y in (0, 1) for x in (0, 1)], dtype=float)
    cube_faces = np.array(
        [[0, 2, 1], [1, 2, 3], [4, 5, 6], [5, 7, 6], [0, 1, 4], [1, 5, 4],
         [2, 6, 3], [3, 6, 7], [0, 4, 2], [2, 4, 6], [1, 3, 5], [3, 7, 5]]
    )  # fmt: skip
    demo_points = np.vstack([cube_points + [3.0 * i, 0.0, 0.0] for i in range(3)])
    demo_faces = np.vstack([cube_faces + 8 * i for i in range(3)])
    demo_file = Path(tempfile.mkdtemp()) / "cubes.dxf"
    write_dxf_fast(demo_points, demo_faces, demo_file)
    return (demo_file,)


@app.cell
def _(demo_file, mo):
    dxf_file = mo.ui.text(value=str(demo_file), label="DXF file", full_width=True)
    decimals = mo.ui.slider(0, 9, value=6, label="Decimals used to merge vertices")
    mo.vstack([dxf_file, decimals])
    return decimals, dxf_file


@app.cell
def _(decimals, dxf_file, mo, parse_dxf_fast):
    raw = parse_dxf_fast(dxf_file.value, decimals=decimals.value)
    n_components = int(raw["labels"].max()) + 1 if len(raw["labels"]) else 0
    mo.md(
        f"""
        ## Raw mesh

        | | |
        |---|---|
        | Points | {len(raw["points"]):,} |
        | Triangles | {len(raw["faces"]):,} |
        | Connected components | {n_components:,} |
        """
    )
    return (n_components,)


@app.cell
def _(decimals, dxf_file, dxf_to_manifold_meshes):
    parts = dxf_to_manifold_meshes(dxf_file.value, use_pyvista=False, decimals=decimals.value)
    return (parts,)


@app.cell
def _(mo, n_components):
    component = mo.ui.slider(0, max(n_components - 1, 0), value=0, label="Component")
    component
    return (component,)


@app.cell
def _(component, diagnose_mesh, mo, parts):
    info = diagnose_mesh(parts[component.value]) if parts else None
    mo.md("No geometry found.") if info is None else mo.md(
        f"""
        ## Component {component.value}

        - {info["n_points"]} points, {info["n_faces"]} triangles
        - x: {info["bounds"]["x"]}, y: {info["bounds"]["y"]}, z: {info["bounds"]["z"]}
        """
    )
    return


if __name__ == "__main__":
    app.run()
