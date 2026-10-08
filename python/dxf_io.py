"""
dxf_io wrapper — Fast Rust DXF parser with optional PyVista integration.

This module wraps the compiled Rust extension to provide:
  • Fast DXF parsing (10-100x speedup)
  • Point deduplication with parallel rayon
  • Connected components extraction
  • DXF writing (round-trip support)
  • Optional PyVista integration for mesh operations
  • Attribute/metadata support
"""

from __future__ import annotations

import logging
from typing import Optional, Union, NamedTuple

import numpy as np
from numpy.typing import NDArray

# Try to import PyVista, but make it optional
try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False
    pv = None  # type: ignore

# Import compiled Rust module
try:
    from . import dxf_io as _rs
except ImportError:
    import dxf_io as _rs

NDArrayFloat = NDArray[np.float64]
NDArrayInt = NDArray[np.intp]


class _RawMesh(NamedTuple):
    """Deduplicated all-triangle mesh from Rust parser."""
    points: NDArrayFloat
    faces: NDArray[np.intp]
    n_components: int
    labels: NDArray[np.intp]


# ============================================================================
# Core Parsing Functions
# ============================================================================


def parse_dxf_fast(
    dxf_file: str,
    decimals: int = 6,
) -> _RawMesh:
    """
    Parse a DXF file using fast Rust implementation.

    Parameters
    ----------
    dxf_file : str
        Path to ASCII DXF file.
    decimals : int
        Decimal places for vertex equality (default: 6).

    Returns
    -------
    _RawMesh
        Named tuple with ``points`` (M, 3), ``faces`` (F, 3),
        ``n_components``, and ``labels`` (F,).

    Examples
    --------
    >>> raw = parse_dxf_fast("building.dxf", decimals=6)
    >>> print(f"Found {raw.n_components} components with {raw.points.shape[0]} unique points")
    """
    rs_raw = _rs.parse_dxf_fast(dxf_file, decimals)

    return _RawMesh(
        points=rs_raw.points_array().astype(np.float64),
        faces=rs_raw.faces_array().astype(np.intp),
        n_components=rs_raw.n_components,
        labels=rs_raw.labels_array().astype(np.intp),
    )


def write_dxf_fast(
    filepath: str,
    raw_mesh: _RawMesh,
) -> None:
    """
    Write a RawMesh to DXF format.

    Parameters
    ----------
    filepath : str
        Output DXF file path.
    raw_mesh : _RawMesh
        Mesh data from parse_dxf_fast() or dxf_to_manifold_meshes().

    Examples
    --------
    >>> raw = parse_dxf_fast("input.dxf")
    >>> write_dxf_fast("output.dxf", raw)
    """
    # Create Rust RawMesh and call write
    rs_raw = _rs.RawMesh(
        points=raw_mesh.points.tolist(),
        faces=raw_mesh.faces.tolist(),
        n_components=raw_mesh.n_components,
        labels=raw_mesh.labels.tolist(),
    )
    rs_raw.to_dxf(filepath)


# ============================================================================
# PyVista Integration (Optional)
# ============================================================================


def _extract_component(
    points: NDArrayFloat,
    faces: NDArray[np.intp],
    mask: NDArray[np.bool_],
    attributes: Optional[dict] = None,
) -> Union[pv.PolyData, dict]:
    """
    Build a triangular mesh for a subset of triangles.

    Can return PyVista PolyData (if available) or dict representation.

    Parameters
    ----------
    points : ndarray of shape (M, 3)
        Global point table.
    faces : ndarray of shape (F, 3)
        Global triangle vertex indices.
    mask : ndarray of shape (F,)
        True for triangles in this component.
    attributes : dict, optional
        Cell data to attach to the mesh.

    Returns
    -------
    pyvista.PolyData or dict
        Triangular mesh. Returns dict if PyVista unavailable.
    """
    sub_faces: NDArray[np.intp] = faces[mask]
    used_verts: NDArray[np.intp] = np.unique(sub_faces)
    local: NDArray[np.int32] = np.searchsorted(used_verts, sub_faces).astype(np.int32)

    n_tri = local.shape[0]
    pv_faces = np.empty((n_tri, 4), dtype=np.int32)
    pv_faces[:, 0] = 3
    pv_faces[:, 1:] = local

    mesh_data = {
        "points": points[used_verts].astype(np.float32),
        "faces": pv_faces.ravel(),
        "n_points": len(used_verts),
        "n_faces": n_tri,
    }

    # Add attributes if provided
    if attributes:
        mesh_data["attributes"] = {k: v[mask] for k, v in attributes.items()}

    if HAS_PYVISTA:
        poly = pv.PolyData()
        poly.points = mesh_data["points"]
        poly.faces = mesh_data["faces"]

        if attributes:
            for attr_name, attr_data in mesh_data["attributes"].items():
                poly.cell_data[attr_name] = attr_data

        return poly
    else:
        return mesh_data


def diagnose_mesh(mesh: Union[pv.PolyData, dict]) -> dict:
    """
    Return mesh quality metrics.

    Works with both PyVista PolyData and dict representation.
    """
    if isinstance(mesh, dict):
        return {
            "n_points": mesh["n_points"],
            "n_faces": mesh["n_faces"],
            "is_manifold": None,  # Cannot check without PyVista
            "is_watertight": None,
        }

    if not HAS_PYVISTA:
        raise ImportError("PyVista required for mesh diagnosis")

    nm = mesh.extract_feature_edges(
        boundary_edges=False,
        non_manifold_edges=True,
        feature_edges=False,
        manifold_edges=False,
    )
    boundary = mesh.extract_feature_edges(
        boundary_edges=True,
        non_manifold_edges=False,
        feature_edges=False,
        manifold_edges=False,
    )
    return {
        "n_points": mesh.n_points,
        "n_faces": mesh.n_faces,
        "n_non_manifold_edges": nm.n_cells,
        "n_boundary_edges": boundary.n_cells,
        "is_manifold": nm.n_cells == 0 and boundary.n_cells == 0,
        "is_watertight": boundary.n_cells == 0,
    }


def to_manifold3d(mesh: pv.PolyData):
    """Convert a triangular PolyData to a guaranteed-manifold representation."""
    if not HAS_PYVISTA:
        raise ImportError("PyVista required for manifold3d conversion")

    try:
        import manifold3d
    except ImportError:
        raise ImportError("manifold3d required: pip install manifold3d")

    tri = mesh.triangulate()
    faces = tri.faces.reshape(-1, 4)[:, 1:].astype(np.uint32)
    mesh_obj = manifold3d.Mesh(
        vert_properties=tri.points.astype(np.float32),
        tri_verts=faces,
    )
    return manifold3d.Manifold(mesh_obj)


def from_manifold3d(m) -> pv.PolyData:
    """Convert from manifold3d back to PyVista PolyData."""
    if not HAS_PYVISTA:
        raise ImportError("PyVista required for manifold3d conversion")

    mesh = m.to_mesh()
    n_tri = mesh.tri_verts.shape[0]
    f = np.empty((n_tri, 4), dtype=np.int32)
    f[:, 0] = 3
    f[:, 1:] = mesh.tri_verts
    return pv.PolyData(mesh.vert_properties[:, :3], f.ravel())


# ============================================================================
# Main API
# ============================================================================


def dxf_to_manifold_meshes(
    dxf_file: str,
    decimals: int = 6,
    repair: bool = True,
    min_face_count: int = 4,
    logger: Optional[logging.Logger] = None,
    use_rust: bool = True,
    use_pyvista: bool = True,
    attributes: Optional[dict] = None,
) -> list:
    """
    Parse a DXF file and return one mesh per connected component.

    Parameters
    ----------
    dxf_file : str
        Path to ASCII DXF file.
    decimals : int
        Decimal places for vertex equality (default: 6).
    repair : bool
        Attempt repair on non-manifold components (default: True).
    min_face_count : int
        Discard components with fewer triangles (default: 4).
    logger : Optional[logging.Logger]
        Logger instance (default: None).
    use_rust : bool
        Use fast Rust parser (default: True).
    use_pyvista : bool
        Return PyVista PolyData if available (default: True).
        If False, returns dict representation.
    attributes : dict, optional
        Cell attributes to attach to meshes.

    Returns
    -------
    list of pyvista.PolyData or list of dict
        One mesh per connected component, sorted by descending face count.

    Examples
    --------
    >>> meshes = dxf_to_manifold_meshes("model.dxf", decimals=6, repair=True)
    >>> print(f"Found {len(meshes)} components")
    >>> for i, mesh in enumerate(meshes):
    ...     print(f"  Component {i}: {mesh.n_faces} faces")
    """
    if use_rust:
        raw = parse_dxf_fast(dxf_file, decimals)
    else:
        raise ValueError("Pure Python fallback not available; use use_rust=True")

    if logger is not None:
        logger.info(f"Found {raw.n_components} connected components")

    meshes: list = []

    for comp_id in range(raw.n_components):
        mask: NDArray[np.bool_] = raw.labels == comp_id

        if mask.sum() < min_face_count:
            if logger is not None:
                logger.warning(f"Skipping component #{comp_id}: too few faces ({mask.sum()})")
            continue

        poly = _extract_component(raw.points, raw.faces, mask, attributes)

        # Post-processing (repair, manifold check)
        if HAS_PYVISTA and use_pyvista and isinstance(poly, pv.PolyData):
            if not poly.is_manifold and repair:
                if logger is not None:
                    logger.info(f"Repairing non-manifold component #{comp_id}")
                try:
                    import pymeshfix
                    mf = pymeshfix.MeshFix(poly)
                    mf.repair()
                    poly = mf.mesh
                except ImportError:
                    if logger is not None:
                        logger.warning("pymeshfix not installed; skipping repair")

        meshes.append(poly)

    # Sort by face count (descending)
    if isinstance(meshes[0], dict):
        meshes.sort(key=lambda m: m["n_faces"], reverse=True)
    else:
        meshes.sort(key=lambda m: m.n_faces, reverse=True)

    return meshes


# ============================================================================
# Attribute Support
# ============================================================================


class MeshWithAttributes:
    """Mesh with support for point and cell data (like PyVista)."""

    def __init__(self, points: NDArrayFloat, faces: NDArray[np.intp]):
        self.points = points
        self.faces = faces
        self.point_data: dict = {}
        self.cell_data: dict = {}

    def add_point_data(self, name: str, data: np.ndarray) -> None:
        """Add data per point."""
        assert len(data) == len(self.points), "Data length must match points"
        self.point_data[name] = data

    def add_cell_data(self, name: str, data: np.ndarray) -> None:
        """Add data per cell (triangle)."""
        n_faces = self.faces.shape[0]
        assert len(data) == n_faces, "Data length must match faces"
        self.cell_data[name] = data

    def to_pyvista(self) -> pv.PolyData:
        """Convert to PyVista PolyData."""
        if not HAS_PYVISTA:
            raise ImportError("PyVista required")

        n_tri = self.faces.shape[0]
        pv_faces = np.empty((n_tri, 4), dtype=np.int32)
        pv_faces[:, 0] = 3
        pv_faces[:, 1:] = self.faces

        poly = pv.PolyData(self.points, pv_faces.ravel())

        for name, data in self.point_data.items():
            poly.point_data[name] = data

        for name, data in self.cell_data.items():
            poly.cell_data[name] = data

        return poly
