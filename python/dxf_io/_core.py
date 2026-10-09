"""Python layer on top of the Rust DXF parser/writer.

Wraps the compiled extension (:mod:`dxf_io._dxf_io`) with numpy-friendly helpers,
connected-component extraction, and optional PyVista / manifold3d conversion.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Optional, Union

import numpy as np

from . import _dxf_io as _rs

if TYPE_CHECKING:
    import pyvista as pv

try:  # PyVista is optional.
    import pyvista as _pv

    HAS_PYVISTA = True
except ImportError:  # pragma: no cover - depends on the environment
    _pv = None
    HAS_PYVISTA = False


def parse_dxf_fast(
    dxf_file: Union[str, "os.PathLike[str]"], decimals: int = 6
) -> dict[str, np.ndarray]:
    """Parse the SOLID and 3DFACE entities of an ASCII DXF file.

    Quads are split into two triangles, and vertices that are equal once rounded to
    ``decimals`` places are merged.

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
        content = dxf_file
    else:
        with open(os.fspath(dxf_file), encoding="utf-8", errors="replace") as f:
            content = f.read()

    raw = _rs.parse_dxf_fast(content, decimals)
    return {
        "points": raw.points_array().astype(np.float64),
        "faces": raw.faces_array().astype(np.intp),
        "labels": raw.labels_array().astype(np.intp),
    }


def write_dxf_fast(
    points: np.ndarray,
    faces: np.ndarray,
    output_file: Optional[Union[str, "os.PathLike[str]"]] = None,
) -> str:
    """Write a triangle mesh as 3DFACE entities.

    Parameters
    ----------
    points : numpy.ndarray
        (N, 3) vertex coordinates.
    faces : numpy.ndarray
        (M, 3) vertex indices.
    output_file : str or path-like, optional
        If given, the DXF content is also written to this file.

    Returns
    -------
    str
        The DXF content.
    """
    content = _rs.write_dxf_fast(
        np.asarray(points, dtype=np.float64).tolist(),
        np.asarray(faces, dtype=np.intp).tolist(),
    )
    if output_file is not None:
        with open(os.fspath(output_file), "w", encoding="utf-8") as f:
            f.write(content)
    return content


class MeshWithAttributes:
    """Triangle mesh with optional point and cell data."""

    def __init__(
        self,
        points: np.ndarray,
        faces: np.ndarray,
        labels: Optional[np.ndarray] = None,
        point_data: Optional[dict[str, np.ndarray]] = None,
        cell_data: Optional[dict[str, np.ndarray]] = None,
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

    def to_dxf(self, output_file: Optional[Union[str, "os.PathLike[str]"]] = None) -> str:
        """Export to DXF (3DFACE entities)."""
        return write_dxf_fast(self.points, self.faces, output_file)

    def to_pyvista(self) -> "pv.PolyData":
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


def _extract_component(
    component_id: int, points: np.ndarray, faces: np.ndarray, labels: np.ndarray
) -> MeshWithAttributes:
    """Extract one connected component, renumbering its vertices from zero."""
    point_mask = labels == component_id
    new_index = np.cumsum(point_mask) - 1
    # All three vertices of a face share one component, so testing the first is enough.
    face_mask = labels[faces[:, 0]] == component_id
    return MeshWithAttributes(
        points[point_mask],
        new_index[faces[face_mask]],
        np.zeros(int(point_mask.sum()), dtype=np.intp),
    )


def dxf_to_manifold_meshes(
    dxf_file: Union[str, "os.PathLike[str]"],
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
    meshes: list[Any] = []
    for cid in range(int(np.max(data["labels"])) + 1 if len(data["labels"]) else 0):
        mesh = _extract_component(cid, data["points"], data["faces"], data["labels"])
        meshes.append(mesh.to_pyvista() if use_pyvista and HAS_PYVISTA else mesh)
    return meshes


def diagnose_mesh(mesh: Union[MeshWithAttributes, "pv.PolyData"]) -> dict[str, Any]:
    """Return basic information (counts and bounds) about a mesh."""
    if isinstance(mesh, MeshWithAttributes):
        points, n_faces = mesh.points, mesh.n_faces
    else:
        points, n_faces = np.asarray(mesh.points), int(mesh.n_cells)
    return {
        "n_points": len(points),
        "n_faces": n_faces,
        "bounds": {
            axis: (float(np.min(points[:, i])), float(np.max(points[:, i])))
            for i, axis in enumerate("xyz")
        },
    }


def to_manifold3d(mesh: Union[MeshWithAttributes, "pv.PolyData"]) -> Any:
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
