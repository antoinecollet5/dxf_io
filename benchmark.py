#!/usr/bin/env python3
"""Time every stage of dxf_io on a DXF file (or on a synthetic one).

Usage::

    python benchmark.py model.dxf
    python benchmark.py --synthetic 500          # 4 grids of 500 x 500 quads (~190 MB)
    python benchmark.py model.dxf --ezdxf        # also time ezdxf (pip install ezdxf)

Build the extension in release mode first: ``maturin develop --release``.
"""

from __future__ import annotations

import argparse
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dxf_io import dxf_to_manifold_meshes, parse_dxf_fast, write_dxf_fast


def make_synthetic(n: int, path: Path, parts: int = 4) -> None:
    """Write ``parts`` disjoint n x n grids of 3DFACE quads."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("  0\nSECTION\n  2\nENTITIES\n")
        for part in range(parts):
            off = part * (n + 5)
            for i in range(n):
                for j in range(n):
                    x, y, z = off + i * 0.5, j * 0.5, 0.1 * part
                    corners = [(x, y), (x + 0.5, y), (x + 0.5, y + 0.5), (x, y + 0.5)]
                    f.write("  0\n3DFACE\n  8\n0\n")
                    for k, (cx, cy) in enumerate(corners):
                        f.write(f" {10 + k}\n{cx:.6f}\n {20 + k}\n{cy:.6f}\n {30 + k}\n{z:.6f}\n")
        f.write("  0\nENDSEC\n  0\nEOF\n")


def timed(
    label: str, func: Callable[..., Any], *args: Any, repeat: int = 3, **kwargs: Any
) -> tuple[float, Any]:
    """Run ``func`` ``repeat`` times, print the best time and return ``(best, result)``."""
    best, result = float("inf"), None
    for _ in range(repeat):
        t0 = time.perf_counter()
        result = func(*args, **kwargs)
        best = min(best, time.perf_counter() - t0)
    print(f"  {label:<34s} {best:8.3f} s")
    return best, result


def bench_ezdxf(path: Path) -> float:
    """Time ezdxf reading the file and iterating over its faces (no vertex merging)."""
    import ezdxf

    t0 = time.perf_counter()
    msp = ezdxf.readfile(str(path)).modelspace()
    faces: Any = msp.query("3DFACE SOLID")
    for entity in faces:
        entity.wcs_vertices()
    return time.perf_counter() - t0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("dxf_file", nargs="?", type=Path, help="DXF file to benchmark")
    parser.add_argument("--synthetic", type=int, metavar="N", help="generate N x N grids instead")
    parser.add_argument("--ezdxf", action="store_true", help="also time ezdxf (slow on big files)")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        if args.synthetic:
            path = Path(tmp) / "synthetic.dxf"
            print(f"Generating a synthetic file ({args.synthetic} x {args.synthetic} x 4 quads)...")
            make_synthetic(args.synthetic, path)
        elif args.dxf_file is not None and args.dxf_file.exists():
            path = args.dxf_file
        else:
            parser.error("give an existing DXF file, or --synthetic N")

        print(f"\n{path.name}: {path.stat().st_size / 1e6:.1f} MB\n")
        _, data = timed("parse_dxf_fast", parse_dxf_fast, path)
        n_comp = int(data["labels"].max()) + 1 if len(data["labels"]) else 0
        print(
            f"    -> {len(data['points'])} points, {len(data['faces'])} faces, {n_comp} components"
        )
        timed("dxf_to_manifold_meshes", dxf_to_manifold_meshes, path, use_pyvista=False)
        timed("write_dxf_fast -> str", write_dxf_fast, data["points"], data["faces"])
        out = Path(tmp) / "out.dxf"
        timed("write_dxf_fast -> file", write_dxf_fast, data["points"], data["faces"], out)

        if args.ezdxf:
            print()
            t_ezdxf = bench_ezdxf(path)
            t_dxf_io, _ = timed("parse_dxf_fast (again)", parse_dxf_fast, path)
            print(f"  {'ezdxf (read + iterate faces)':<34s} {t_ezdxf:8.3f} s")
            print(f"\n  dxf_io is {t_ezdxf / t_dxf_io:.0f}x faster than ezdxf")


if __name__ == "__main__":
    main()
