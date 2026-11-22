"""Performance of dxf_io on a synthetic file (optionally compared with ezdxf).

Run with ``marimo edit examples/example_04_performance.py``.
Build the extension in release mode first: ``maturin develop --release``.
"""

import marimo

__generated_with = "0.25.2"
app = marimo.App()


@app.cell
def _():
    import tempfile
    import time
    from pathlib import Path

    import marimo as mo
    import numpy as np

    from dxf_io import dxf_to_manifold_meshes, parse_dxf_fast, write_dxf_fast

    return Path, dxf_to_manifold_meshes, mo, np, parse_dxf_fast, tempfile, time, write_dxf_fast


@app.cell
def _(mo):
    size = mo.ui.slider(50, 1000, step=50, value=300, label="Grid size (n x n quads)")
    parts = mo.ui.slider(1, 100, value=4, label="Disjoint parts")
    compare = mo.ui.checkbox(label="Compare with ezdxf (slow)")
    mo.vstack([size, parts, compare])
    return compare, parts, size


@app.cell
def _(Path, np, parts, size, tempfile, write_dxf_fast):
    def grid(n):
        x, y = np.meshgrid(np.arange(n + 1, dtype=float), np.arange(n + 1, dtype=float))
        pts = np.column_stack([x.ravel(), y.ravel(), np.zeros(x.size)])
        ids = np.arange((n + 1) ** 2).reshape(n + 1, n + 1)
        a, b, c, d = ids[:-1, :-1], ids[:-1, 1:], ids[1:, 1:], ids[1:, :-1]
        tris = np.vstack(
            [np.column_stack([a.ravel(), b.ravel(), c.ravel()]),
             np.column_stack([a.ravel(), c.ravel(), d.ravel()])]
        )  # fmt: skip
        return pts, tris

    n = max(size.value // int(np.sqrt(parts.value)), 1)
    one_pts, one_tris = grid(n)
    all_pts = np.vstack([one_pts + [0.0, 0.0, 2.0 * k] for k in range(parts.value)])
    all_tris = np.vstack([one_tris + k * len(one_pts) for k in range(parts.value)])
    path = Path(tempfile.mkdtemp()) / "synthetic.dxf"
    write_dxf_fast(all_pts, all_tris, path)
    return all_pts, all_tris, path


@app.cell
def _(time):
    def best_of(func, *args, repeat=3, **kwargs):
        """Best wall-clock time of ``repeat`` calls, in seconds."""
        best = float("inf")
        for _ in range(repeat):
            start = time.perf_counter()
            func(*args, **kwargs)
            best = min(best, time.perf_counter() - start)
        return best

    return (best_of,)


@app.cell
def _(all_pts, all_tris, best_of, dxf_to_manifold_meshes, parse_dxf_fast, path, write_dxf_fast):
    timings = {
        "parse_dxf_fast": best_of(parse_dxf_fast, path),
        "dxf_to_manifold_meshes": best_of(dxf_to_manifold_meshes, path, use_pyvista=False),
        "write_dxf_fast (file)": best_of(
            write_dxf_fast, all_pts, all_tris, path.with_suffix(".out")
        ),
        "write_dxf_fast (string)": best_of(write_dxf_fast, all_pts, all_tris),
    }
    return (timings,)


@app.cell
def _(compare, path, time):
    ezdxf_time = None
    if compare.value:
        import ezdxf

        start = time.perf_counter()
        for entity in ezdxf.readfile(str(path)).modelspace().query("3DFACE SOLID"):
            entity.wcs_vertices()
        ezdxf_time = time.perf_counter() - start
    return (ezdxf_time,)


@app.cell
def _(all_tris, ezdxf_time, mo, path, timings):
    rows = "\n".join(f"| {name} | {t * 1000:.1f} ms |" for name, t in timings.items())
    if ezdxf_time is not None:
        speedup = ezdxf_time / timings["parse_dxf_fast"]
        rows += f"\n| ezdxf (read + iterate) | {ezdxf_time * 1000:.0f} ms ({speedup:.0f}x slower) |"
    mo.md(
        f"""
        ## {path.stat().st_size / 1e6:.1f} MB, {len(all_tris):,} triangles

        | Operation | Best of 3 |
        |---|---|
        {rows}
        """
    )
    return


if __name__ == "__main__":
    app.run()
