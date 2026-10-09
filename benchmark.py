#!/usr/bin/env python3
"""
Benchmark: Pure Python vs. Rust + PyO3

Compares performance of dxf_io.py (pure Python) vs.
dxf_io_wrapper.py (Rust + PyO3 bindings).

Run with:
    python benchmark.py <path_to_dxf_file>
"""

import sys
import time
from pathlib import Path
from typing import Tuple

import numpy as np


def bench_parse(func, dxf_file: str, decimals: int = 6, n_runs: int = 3) -> Tuple[float, dict]:
    """Run parser n times, return median time and result."""
    times = []
    result = None

    for i in range(n_runs):
        t0 = time.perf_counter()
        result = func(dxf_file, decimals)
        t1 = time.perf_counter()
        times.append(t1 - t0)
        print(f"  Run {i+1}/{n_runs}: {times[-1]:.3f}s", flush=True)

    times.sort()
    median_time = times[n_runs // 2]

    stats = {
        "min": min(times),
        "median": median_time,
        "max": max(times),
        "mean": np.mean(times),
        "n_points": int(result.points.shape[0]) if hasattr(result, 'points') else None,
        "n_faces": int(result.faces.shape[0]) if hasattr(result, 'faces') else None,
        "n_components": int(result.n_components) if hasattr(result, 'n_components') else None,
    }
    return median_time, stats


def main():
    if len(sys.argv) < 2:
        print("Usage: python benchmark.py <dxf_file>")
        print("Example: python benchmark.py model.dxf")
        sys.exit(1)

    dxf_file = sys.argv[1]
    if not Path(dxf_file).exists():
        print(f"Error: File not found: {dxf_file}")
        sys.exit(1)

    file_size_mb = Path(dxf_file).stat().st_size / (1024 * 1024)
    print(f"Benchmarking: {dxf_file} ({file_size_mb:.1f} MB)\n")

    # Test 1: Import and benchmark Rust version
    print("=" * 60)
    print("RUST + PyO3 (dxf_io_wrapper)")
    print("=" * 60)
    try:
        from dxf_io_wrapper import parse_dxf_fast as rust_parse

        print("Parsing (3 runs)...")
        rust_time, rust_stats = bench_parse(rust_parse, dxf_file, n_runs=3)

        print(f"\nResults:")
        print(f"  Points: {rust_stats['n_points']}")
        print(f"  Faces: {rust_stats['n_faces']}")
        print(f"  Components: {rust_stats['n_components']}")
        print(f"  Time: {rust_time:.3f}s (min={rust_stats['min']:.3f}, max={rust_stats['max']:.3f})")

    except ImportError as e:
        print(f"⚠️  Rust version not available: {e}")
        print("   Run: maturin develop -r\n")
        rust_time = None
        rust_stats = None

    # Test 2: Import and benchmark pure Python version
    print("\n" + "=" * 60)
    print("PURE PYTHON (dxf_io.dxf_to_manifold_meshes)")
    print("=" * 60)
    try:
        from dxf_io import dxf_to_manifold_meshes as python_parse

        print("Parsing (1 run, may be slow)...")

        t0 = time.perf_counter()
        py_meshes = python_parse(dxf_file, decimals=6, repair=False)
        python_time = time.perf_counter() - t0

        py_n_points = sum(m.n_points for m in py_meshes)
        py_n_faces = sum(m.n_faces for m in py_meshes)

        print(f"\nResults:")
        print(f"  Points: {py_n_points}")
        print(f"  Faces: {py_n_faces}")
        print(f"  Components: {len(py_meshes)}")
        print(f"  Time: {python_time:.3f}s")

    except ImportError as e:
        print(f"⚠️  Pure Python version not available: {e}")
        print("   Ensure dxf_io.py is in PYTHONPATH\n")
        python_time = None

    # Comparison
    print("\n" + "=" * 60)
    print("COMPARISON")
    print("=" * 60)

    if rust_time and python_time:
        speedup = python_time / rust_time
        print(f"Rust: {rust_time:.3f}s")
        print(f"Python: {python_time:.3f}s")
        print(f"Speedup: {speedup:.1f}x faster with Rust\n")

        if rust_stats and abs(rust_stats['n_faces'] - py_n_faces) > 0:
            print(f"⚠️  Face count mismatch: Rust={rust_stats['n_faces']}, Python={py_n_faces}")
        else:
            print("✅ Results match between implementations")
    elif rust_time:
        print(f"Rust: {rust_time:.3f}s")
        print("(Python version not available for comparison)")
    elif python_time:
        print(f"Python: {python_time:.3f}s")
        print("(Rust version not available for comparison)")


if __name__ == "__main__":
    main()
