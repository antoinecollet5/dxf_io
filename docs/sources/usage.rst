.. _user_guide_ref:

==========
User guide
==========

This guide walks through the main features of dxf_io. Every snippet can be run as is:
the first one writes the ``cubes.dxf`` file used by the following ones.

Writing a DXF file
------------------

:func:`~dxf_io.write_dxf_fast` writes a triangle mesh, given as ``(N, 3)`` points and
``(M, 3)`` vertex indices, as ``3DFACE`` entities. Here, three disjoint unit cubes:

.. code-block:: python

    import numpy as np

    from dxf_io import write_dxf_fast

    cube_points = np.array([[x, y, z] for z in (0, 1) for y in (0, 1) for x in (0, 1)], float)
    cube_faces = np.array([
        [0, 2, 1], [1, 2, 3], [4, 5, 6], [5, 7, 6], [0, 1, 4], [1, 5, 4],
        [2, 6, 3], [3, 6, 7], [0, 4, 2], [2, 4, 6], [1, 3, 5], [3, 7, 5],
    ])
    points = np.vstack([cube_points + [3.0 * i, 0.0, 0.0] for i in range(3)])
    faces = np.vstack([cube_faces + 8 * i for i in range(3)])

    write_dxf_fast(points, faces, "cubes.dxf")  # streamed to the file
    text = write_dxf_fast(points, faces)        # or returned as a string

Coordinates are written with six decimals. Writing is parallel and streams to the file,
so the whole document is never held in memory.

Reading a DXF file
------------------

:func:`~dxf_io.parse_dxf_fast` reads the ``SOLID`` and ``3DFACE`` entities of an ASCII
DXF file (other entities are ignored) and returns NumPy arrays:

.. code-block:: python

    from dxf_io import parse_dxf_fast

    mesh = parse_dxf_fast("cubes.dxf")
    mesh["points"]  # (N, 3) float64: vertex coordinates
    mesh["faces"]   # (M, 3) intp: triangles, as indices into points
    mesh["labels"]  # (N,) intp: connected-component id of each vertex

    print(len(mesh["points"]), len(mesh["faces"]), mesh["labels"].max() + 1)  # 24 36 3

The argument can also be the DXF content itself (any string containing a newline).

How entities become triangles
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Vertices that are equal once rounded to ``decimals`` places (6 by default) are
  merged, so that adjacent faces share their vertices. Vertices are numbered in order of
  first appearance in the file.
- An entity whose 4th corner is missing, or equal to its 3rd corner (DXF convention) or
  to its 1st corner (a common exporter shortcut), is a triangle. Other entities are
  quads, split into two triangles. ``SOLID`` corners are read in the DXF "zig-zag" order.
- Degenerate triangles (with a repeated vertex) are dropped.

.. code-block:: python

    coarse = parse_dxf_fast("cubes.dxf", decimals=0)  # merge vertices closer than ~0.5

Splitting into connected components
-----------------------------------

:func:`~dxf_io.dxf_to_manifold_meshes` returns one mesh per connected component (groups
of triangles sharing vertices), with vertices renumbered from zero. It runs in linear
time, whatever the number of components.

.. code-block:: python

    from dxf_io import diagnose_mesh, dxf_to_manifold_meshes

    parts = dxf_to_manifold_meshes("cubes.dxf", use_pyvista=False)
    for part in parts:
        info = diagnose_mesh(part)
        print(part.n_points, part.n_faces, info["bounds"]["x"])
    # 8 12 (0.0, 1.0)
    # 8 12 (3.0, 4.0)
    # 8 12 (6.0, 7.0)

With ``use_pyvista=True`` (the default) and PyVista installed, the components are
returned as :class:`pyvista.PolyData` objects; otherwise as
:class:`~dxf_io.MeshWithAttributes`.

Meshes with attributes and PyVista
----------------------------------

:class:`~dxf_io.MeshWithAttributes` stores a triangle mesh with optional point and cell
data, and converts it to PyVista (``pip install "dxf_io[visualization]"``) or back to
DXF:

.. code-block:: python

    from dxf_io import MeshWithAttributes

    part = parts[0]
    triangles = part.points[part.faces]
    area = 0.5 * np.linalg.norm(
        np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1
    )
    mesh = MeshWithAttributes(
        part.points,
        part.faces,
        point_data={"elevation": part.points[:, 2]},
        cell_data={"area": area},
    )
    mesh.to_dxf("first_cube.dxf")

    poly = mesh.to_pyvista()  # requires PyVista
    poly.plot(scalars="area")

manifold3d
----------

:func:`~dxf_io.to_manifold3d` and :func:`~dxf_io.from_manifold3d` convert meshes to and
from :class:`manifold3d.Manifold` (``pip install "dxf_io[manifold]"``), for example to
compute boolean operations on closed meshes:

.. code-block:: python

    from dxf_io import from_manifold3d, to_manifold3d

    union = to_manifold3d(parts[0]) + to_manifold3d(parts[1])
    result = from_manifold3d(union)
    print(result.n_faces)  # 24

Performance tips
----------------

- Pass a path rather than the file content: the file is then read by Rust, without
  creating a Python string.
- Write to a file rather than to a string for large meshes: the output is streamed.
- Parsing and writing release the GIL, so other Python threads keep running, and several
  files can be processed at once from a thread pool. On free-threaded Python builds, the
  GIL stays disabled.
- Large files are split into chunks parsed in parallel on all the available cores. The
  number of threads can be limited with the ``RAYON_NUM_THREADS`` environment variable.

Interactive examples
--------------------

The `examples folder <https://github.com/antoinecollet5/dxf_io/tree/master/examples>`_
of the repository contains `marimo <https://marimo.io>`_ notebooks (basic parsing, DXF
writing and round trip, attributes, performance). Open one with:

.. code-block:: console

    $ pip install marimo "dxf_io[visualization]"
    $ marimo edit examples/example_01_basic_parsing.py
