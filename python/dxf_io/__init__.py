"""
dxf_io: fast Rust-based DXF mesh reader and writer, with optional PyVista support.

Provides 10-100x speedup over pure Python implementations for large
mesh files (100K+ faces). Includes optional PyVista integration and
DXF writing capabilities.

Basic Usage:
    >>> from dxf_io import dxf_to_manifold_meshes
    >>> meshes = dxf_to_manifold_meshes("model.dxf")
    >>> for i, mesh in enumerate(meshes):
    ...     print(f"Component {i}: {mesh.n_faces} faces")
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
