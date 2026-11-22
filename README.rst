=================
dxf_io
=================

|License| |Python| |PyPI| |Build Status| |codecov| |Ruff| |ty|

🚀 **Fast Rust-based DXF mesh reader and writer, with optional PyVista support** — 10–100x faster than pure Python (ezdxf).

``dxf_io`` reads the ``SOLID`` and ``3DFACE`` entities of ASCII DXF files into NumPy
arrays (merging duplicate vertices and finding connected components), and writes
triangle meshes back as ``3DFACE`` entities.

**The complete documentation can be found here**: `GitHub Repository <https://github.com/antoinecollet5/dxf_io>`_.

===============
📦 Installation
===============

Pre-built wheels are available for Linux (x86_64, aarch64; glibc and musl), macOS
(Intel and Apple Silicon) and Windows (x64, ARM64), for CPython 3.10 to 3.15, including
free-threaded builds:

.. code-block:: bash

    pip install dxf_io                  # NumPy only
    pip install "dxf_io[visualization]" # + PyVista
    pip install "dxf_io[all]"           # + PyVista and manifold3d

Installing from source requires a `Rust toolchain <https://rustup.rs>`_.

==============
🧭 Quick start
==============

.. code-block:: python

    from dxf_io import dxf_to_manifold_meshes, parse_dxf_fast, write_dxf_fast

    # Raw arrays: points (N, 3) float64, faces (M, 3) and labels (N,) intp.
    mesh = parse_dxf_fast("model.dxf", decimals=6)
    print(mesh["points"].shape, mesh["faces"].shape)

    # One mesh per connected component (pyvista.PolyData if PyVista is installed).
    parts = dxf_to_manifold_meshes("model.dxf", use_pyvista=False)
    for part in parts:
        print(part.n_points, part.n_faces)

    # Write a triangle mesh (to a file, or to a string when no file is given).
    write_dxf_fast(mesh["points"], mesh["faces"], "out.dxf")

===============
⚡ Performance
===============

Parsing, vertex merging and writing run in Rust, use all the available cores and release
the GIL. On a 67 MB file (360,000 vertices, 720,000 triangles), parsing takes about
0.15 s and writing about 0.2 s on a 2-core machine, about 65x faster than
`ezdxf <https://ezdxf.mozman.at>`_ merely reading and iterating the faces (``dxf_io``
also merges the vertices and finds the connected components). Splitting a mesh into its
components is linear in its size, whatever the number of components.

Reproduce with ``python benchmark.py --synthetic 300 --ezdxf`` after
``maturin develop --release``.

==============
🛠️ Development
==============

.. code-block:: bash

    uv sync                               # builds the extension, installs dev tools
    uv run pytest && cargo test           # Python and Rust tests
    uv run ruff check . && uv run ruff format --check . && uv run ty check

See `CONTRIBUTING.md <https://github.com/antoinecollet5/dxf_io/blob/main/CONTRIBUTING.md>`_
for the release process.

===========
🔑 License
===========

This project is released under the **BSD 3-Clause License**.

Copyright (c) 2026, Antoine COLLET. All rights reserved.

For more details, see the `LICENSE <https://github.com/antoinecollet5/dxf_io/blob/main/LICENSE>`_ file.

==============
⚠️ Disclaimer
==============

This software is provided "as is", without warranty of any kind, express or implied.
In no event shall the authors be liable for any damages arising from use of this software.

By using this software, you agree to accept full responsibility for any consequences.

============
📧 Contact
============

For questions, suggestions, or contributions:

- Email: `antoine.collet5@gmail.com <mailto:antoine.collet5@gmail.com>`_
- GitHub: `dxf_io <https://github.com/antoinecollet5/dxf_io>`_

Contributions are welcome!

=============
📚 References
=============

- `PyO3 Documentation <https://pyo3.rs>`_
- `Maturin <https://github.com/PyO3/maturin>`_
- `rayon - data parallelism <https://github.com/rayon-rs/rayon>`_
- `PyVista <https://docs.pyvista.org>`_

.. |License| image:: https://img.shields.io/badge/License-BSD_3--Clause-blue.svg
    :target: https://github.com/antoinecollet5/dxf_io/blob/main/LICENSE
    :alt: License

.. |Python| image:: https://img.shields.io/pypi/pyversions/dxf_io.svg
    :target: https://pypi.org/project/dxf_io/
    :alt: Python

.. |PyPI| image:: https://img.shields.io/pypi/v/dxf_io.svg
    :target: https://pypi.org/project/dxf_io/
    :alt: PyPI

.. |Build Status| image:: https://github.com/antoinecollet5/dxf_io/actions/workflows/main.yml/badge.svg
    :target: https://github.com/antoinecollet5/dxf_io/actions/workflows/main.yml
    :alt: Build Status

.. |codecov| image:: https://codecov.io/gh/antoinecollet5/dxf_io/graph/badge.svg?token=CxdQ0SkRbx
    :target: https://codecov.io/gh/antoinecollet5/dxf_io
    :alt: Code Coverage

.. |Ruff| image:: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json
    :target: https://github.com/astral-sh/ruff
    :alt: Ruff

.. |ty| image:: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ty/main/assets/badge/v0.json
    :target: https://github.com/astral-sh/ty
    :alt: Checked with ty
