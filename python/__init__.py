"""
dxf_io: Fast Rust-based DXF mesh reader-writer with pyvista and shapely support.

Provides 10-100x speedup over pure Python implementations for large
mesh files (100K+ faces). Includes optional PyVista integration and
DXF writing capabilities.

Basic Usage:
    >>> from dxf_io import dxf_to_manifold_meshes
    >>> meshes = dxf_to_manifold_meshes("model.dxf")
    >>> for i, mesh in enumerate(meshes):
    ...     print(f"Component {i}: {mesh.n_faces} faces")
"""

from .dxf_io import (
    MeshWithAttributes,
    dxf_to_manifold_meshes,
    parse_dxf_fast,
    write_dxf_fast,
)

__version__ = "0.1.0"
__all__ = [
    "dxf_to_manifold_meshes",
    "parse_dxf_fast",
    "write_dxf_fast",
    "MeshWithAttributes",
]
