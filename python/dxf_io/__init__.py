"""
Purpose
=======

**dxf_io** is a fast DXF mesh reader and writer written in Rust. It reads the
``SOLID`` and ``3DFACE`` entities of ASCII DXF files into NumPy arrays (merging
duplicate vertices and labelling connected components) and writes triangle meshes back
as ``3DFACE`` entities, using all the available cores and without holding the GIL.

The following functionalities are directly provided on module-level.

Reading and writing
===================

.. autosummary::
   :toctree: _autosummary

   parse_dxf_fast
   dxf_to_manifold_meshes
   write_dxf_fast

Meshes
======

.. autosummary::
   :toctree: _autosummary

   MeshWithAttributes

Utilities
=========

.. autosummary::
   :toctree: _autosummary

   diagnose_mesh
   to_manifold3d
   from_manifold3d

"""

from importlib import metadata as _metadata

from ._core import (
    MeshWithAttributes,
    diagnose_mesh,
    dxf_to_manifold_meshes,
    from_manifold3d,
    parse_dxf_fast,
    to_manifold3d,
    write_dxf_fast,
)

try:
    __version__ = _metadata.version("dxf_io")
except _metadata.PackageNotFoundError:  # pragma: no cover - not installed
    __version__ = "0.0.0"
__all__ = [
    "MeshWithAttributes",
    "diagnose_mesh",
    "dxf_to_manifold_meshes",
    "from_manifold3d",
    "parse_dxf_fast",
    "to_manifold3d",
    "write_dxf_fast",
]
