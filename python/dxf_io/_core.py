"""Python layer on top of the Rust DXF parser/writer.

Wraps the compiled extension (:mod:`dxf_io._dxf_io`) with numpy-friendly helpers,
connected-component extraction, and optional PyVista / manifold3d conversion.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, overload

import numpy as np

try:
    from . import _dxf_io as _rs
except ImportError as exc:  # pragma: no cover - depends on the installation
    import sys

    raise ImportError(
        "The compiled extension of dxf_io (dxf_io._dxf_io) is missing or was built for "
        f"another Python version (this is Python {sys.version_info.major}."
        f"{sys.version_info.minor}). In a development checkout, rebuild it with "
        "`maturin develop --release` (or `uv sync --reinstall-package dxf_io`); "
        "otherwise reinstall dxf_io with pip."
    ) from exc

if TYPE_CHECKING:
    import pyvista as pv

try:  # PyVista is optional.
    import pyvista as _pv

    HAS_PYVISTA = True
except ImportError:  # pragma: no cover - depends on the environment
    _pv = None
    HAS_PYVISTA = False


def parse_dxf_fast(dxf_file: str | os.PathLike[str], decimals: int = 6) -> dict[str, np.ndarray]:
    """Parse the SOLID and 3DFACE entities of an ASCII DXF file.

    Quads are split into two triangles, and vertices that are equal once rounded to
    ``decimals`` places are merged. An entity whose 4th corner is missing, or equal to
    its 3rd corner (DXF convention) or to its 1st one (common exporter shortcut) once
    rounded, is a triangle. SOLID corners are in the DXF "zig-zag" order.

    Files are read and parsed in Rust, using all the available cores, without holding
    the GIL.

    Parameters
    ----------
    dxf_file : str or path-like
        Path to a DXF file, or the DXF content itself (any string containing a newline).
    decimals : int, optional
        Number of decimal places used to decide that two vertices are identical.

    Returns
    -------
    dict
        ``"points"`` (N, 3) float64, ``"faces"`` (M, 3) intp and ``"labels"`` (N,) intp,
        the connected-component id of each point.
    """
    if isinstance(dxf_file, str) and "\n" in dxf_file:
        points, faces, labels = _rs.parse_dxf_bytes(dxf_file.encode("utf-8"), decimals)
    else:
        points, faces, labels = _rs.parse_dxf_file(dxf_file, decimals)
    return {
        "points": points,
        "faces": faces.astype(np.intp, copy=False),
        "labels": labels.astype(np.intp, copy=False),
    }


@overload
def write_dxf_fast(points: np.ndarray, faces: np.ndarray, output_file: None = None) -> str: ...
@overload
def write_dxf_fast(
    points: np.ndarray, faces: np.ndarray, output_file: str | os.PathLike[str]
) -> None: ...
def write_dxf_fast(
    points: np.ndarray,
    faces: np.ndarray,
    output_file: str | os.PathLike[str] | None = None,
) -> str | None:
    """Write a triangle mesh as 3DFACE entities.

    Parameters
    ----------
    points : numpy.ndarray
        (N, 3) vertex coordinates.
    faces : numpy.ndarray
        (M, 3) vertex indices.
    output_file : str or path-like, optional
        If given, the DXF is streamed to this file and nothing is returned. This avoids
        building the whole document in memory.

    Returns
    -------
    str or None
        The DXF content if ``output_file`` is None, otherwise None.

    Raises
    ------
    ValueError
        If the arrays do not have shape (N, 3) or a face index is out of range.
    """
    pts = np.ascontiguousarray(points, dtype=np.float64)
    fcs = np.ascontiguousarray(faces, dtype=np.int64)
    if pts.ndim != 2 or fcs.ndim != 2:
        raise ValueError("points and faces must be 2D arrays of shape (N, 3)")
    if output_file is None:
        return _rs.write_dxf_string(pts, fcs)
    _rs.write_dxf_file(output_file, pts, fcs)
    return None


class MeshWithAttributes:
    """Triangle mesh with optional point and cell data."""

    def __init__(
        self,
        points: np.ndarray,
        faces: np.ndarray,
        labels: np.ndarray | None = None,
        point_data: dict[str, np.ndarray] | None = None,
        cell_data: dict[str, np.ndarray] | None = None,
    ) -> None:
        self.points = np.asarray(points, dtype=np.float64)
        self.faces = np.asarray(faces, dtype=np.intp)
        self.labels = (
            np.zeros(len(self.points), dtype=np.intp)
            if labels is None
            else np.asarray(labels, dtype=np.intp)
        )
        self.point_data: dict[str, np.ndarray] = point_data or {}
        self.cell_data: dict[str, np.ndarray] = cell_data or {}

    @property
    def n_points(self) -> int:
        """Number of vertices."""
        return len(self.points)

    @property
    def n_faces(self) -> int:
        """Number of triangles."""
        return len(self.faces)

    @property
    def n_components(self) -> int:
        """Number of connected components."""
        return int(np.max(self.labels)) + 1 if len(self.labels) else 0

    @overload
    def to_dxf(self, output_file: None = None) -> str: ...
    @overload
    def to_dxf(self, output_file: str | os.PathLike[str]) -> None: ...
    def to_dxf(self, output_file: str | os.PathLike[str] | None = None) -> str | None:
        """Export to DXF (3DFACE entities). See :func:`write_dxf_fast`."""
        return write_dxf_fast(self.points, self.faces, output_file)

    def to_pyvista(self) -> pv.PolyData:
        """Convert to a :class:`pyvista.PolyData` (requires PyVista)."""
        if _pv is None:
            raise ImportError("PyVista is required: pip install dxf_io[visualization]")
        cells = np.hstack((np.full((len(self.faces), 1), 3, dtype=np.intp), self.faces))
        poly = _pv.PolyData(self.points, cells.ravel())
        for name, data in self.point_data.items():
            poly.point_data[name] = data
        for name, data in self.cell_data.items():
            poly.cell_data[name] = data
        return poly


def _split_components(
    points: np.ndarray, faces: np.ndarray, labels: np.ndarray
) -> list[MeshWithAttributes]:
    """Split a mesh into its connected components, renumbering vertices from zero.

    Runs in O(N) whatever the number of components: points and faces are grouped by
    component with one stable (radix) sort each, and every component is a slice.
    Vertices and faces keep their original relative order inside each component.
    """
    n_comp = int(labels.max()) + 1 if len(labels) else 0
    point_order = np.argsort(labels, kind="stable")
    point_counts = np.bincount(labels, minlength=n_comp)
    point_starts = np.concatenate(([0], np.cumsum(point_counts)))
    # Index of every point inside its own component.
    local = np.empty(len(labels), dtype=np.intp)
    local[point_order] = np.arange(len(labels)) - np.repeat(point_starts[:-1], point_counts)
    # All three vertices of a face share one component, so the first one is enough.
    face_labels = labels[faces[:, 0]]
    face_order = np.argsort(face_labels, kind="stable")
    face_starts = np.concatenate(([0], np.cumsum(np.bincount(face_labels, minlength=n_comp))))
    sorted_points = points[point_order]
    sorted_faces = local[faces[face_order]]
    return [
        MeshWithAttributes(
            sorted_points[point_starts[c] : point_starts[c + 1]],
            sorted_faces[face_starts[c] : face_starts[c + 1]],
            np.zeros(int(point_counts[c]), dtype=np.intp),
        )
        for c in range(n_comp)
    ]


def dxf_to_manifold_meshes(
    dxf_file: str | os.PathLike[str],
    use_pyvista: bool = True,
    decimals: int = 6,
) -> list[Any]:
    """Parse a DXF file and split it into its connected components.

    Parameters
    ----------
    dxf_file : str or path-like
        Path to a DXF file, or its content.
    use_pyvista : bool, optional
        Return :class:`pyvista.PolyData` objects when PyVista is installed.
        Otherwise :class:`MeshWithAttributes` objects are returned.
    decimals : int, optional
        Number of decimal places used to merge identical vertices.

    Returns
    -------
    list
        One mesh per connected component.
    """
    data = parse_dxf_fast(dxf_file, decimals)
    meshes = _split_components(data["points"], data["faces"], data["labels"])
    if use_pyvista and HAS_PYVISTA:
        return [mesh.to_pyvista() for mesh in meshes]
    return list(meshes)


def diagnose_mesh(mesh: MeshWithAttributes | pv.PolyData) -> dict[str, Any]:
    """Return basic information (counts and bounds) about a mesh.

    Bounds are NaN for a mesh without points.
    """
    if isinstance(mesh, MeshWithAttributes):
        points, n_faces = mesh.points, mesh.n_faces
    else:
        points, n_faces = np.asarray(mesh.points), int(mesh.n_cells)
    if len(points):
        lo, hi = points.min(axis=0), points.max(axis=0)
        bounds = {axis: (float(lo[i]), float(hi[i])) for i, axis in enumerate("xyz")}
    else:
        bounds = {axis: (float("nan"), float("nan")) for axis in "xyz"}
    return {"n_points": len(points), "n_faces": n_faces, "bounds": bounds}


def to_manifold3d(mesh: MeshWithAttributes | pv.PolyData) -> Any:
    """Convert a mesh to a :class:`manifold3d.Manifold` (requires manifold3d)."""
    try:
        import manifold3d
    except ImportError as e:
        raise ImportError("manifold3d is required: pip install dxf_io[manifold]") from e

    if isinstance(mesh, MeshWithAttributes):
        points, faces = mesh.points, mesh.faces
    else:
        points, faces = np.asarray(mesh.points), mesh.faces.reshape(-1, 4)[:, 1:4]
    return manifold3d.Manifold(
        manifold3d.Mesh(
            vert_properties=np.asarray(points, dtype=np.float32),
            tri_verts=np.asarray(faces, dtype=np.uint32),
        )
    )


def from_manifold3d(manifold: Any) -> MeshWithAttributes:
    """Convert a :class:`manifold3d.Manifold` back to a :class:`MeshWithAttributes`."""
    mesh = manifold.to_mesh()
    return MeshWithAttributes(mesh.vert_properties[:, :3], mesh.tri_verts)
