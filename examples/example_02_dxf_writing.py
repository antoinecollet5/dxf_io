"""DXF writing and round trip with dxf_io: parse, transform, write, re-read.

Run with ``marimo edit examples/example_02_dxf_writing.py``.
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

    from dxf_io import parse_dxf_fast, write_dxf_fast

    return Path, mo, np, parse_dxf_fast, tempfile, write_dxf_fast


@app.cell
def _(Path, np, tempfile, write_dxf_fast):
    # A demo file: a 20 x 20 grid of triangles on a wavy surface.
    n = 21
    x, y = np.meshgrid(np.arange(n, dtype=float), np.arange(n, dtype=float))
    z = np.sin(x / 3) * np.cos(y / 3)
    grid_points = np.column_stack([x.ravel(), y.ravel(), z.ravel()])
    ids = np.arange(n * n).reshape(n, n)
    a, b, c, d = ids[:-1, :-1], ids[:-1, 1:], ids[1:, 1:], ids[1:, :-1]
    grid_faces = np.vstack(
        [np.column_stack([a.ravel(), b.ravel(), c.ravel()]),
         np.column_stack([a.ravel(), c.ravel(), d.ravel()])]
    )  # fmt: skip
    workdir = Path(tempfile.mkdtemp())
    input_file = workdir / "surface.dxf"
    write_dxf_fast(grid_points, grid_faces, input_file)
    return input_file, workdir


@app.cell
def _(mo):
    scale = mo.ui.slider(0.1, 10.0, step=0.1, value=2.0, label="Scale factor")
    shift_z = mo.ui.number(value=100.0, label="Shift along z")
    mo.vstack([scale, shift_z])
    return scale, shift_z


@app.cell
def _(input_file, parse_dxf_fast, scale, shift_z):
    mesh = parse_dxf_fast(input_file)
    new_points = mesh["points"] * scale.value + [0.0, 0.0, shift_z.value]
    return mesh, new_points


@app.cell
def _(mesh, mo, new_points, workdir, write_dxf_fast):
    output_file = workdir / "surface_transformed.dxf"
    write_dxf_fast(new_points, mesh["faces"], output_file)
    preview = write_dxf_fast(new_points[:3], mesh["faces"][:0])  # header only, as a string
    mo.md(
        f"Wrote `{output_file}` ({output_file.stat().st_size / 1e3:.0f} kB). "
        f"Without a file, `write_dxf_fast` returns the DXF text ({len(preview)} characters "
        "for an empty mesh)."
    )
    return (output_file,)


@app.cell
def _(mesh, mo, new_points, np, output_file, parse_dxf_fast):
    again = parse_dxf_fast(output_file)
    same_shape = again["faces"].shape == mesh["faces"].shape
    max_error = float(np.abs(again["points"] - new_points).max())
    mo.md(
        f"""
        ## Round trip

        - Same number of triangles: {"✅" if same_shape else "❌"}
        - Largest coordinate error: {max_error:.2e} (coordinates are written with 6 decimals)
        """
    )
    return


if __name__ == "__main__":
    app.run()
