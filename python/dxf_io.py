"""
dxf_io: Fast Rust-based DXF mesh parser with PyO3 bindings.

Provides 10-100x speedup over pure Python implementations for large
mesh files (100K+ faces). Includes optional PyVista integration and
DXF writing capabilities.

Basic Usage:
    >>> from dxf_io import dxf_to_manifold_meshes
    >>> meshes = dxf_to_manifold_meshes("model.dxf")
    >>> for i, mesh in enumerate(meshes):
    ...     print(f"Component {i}: {mesh.n_faces} faces")
"""

from typing import TYPE_CHECKING, Any, NamedTuple, Optional, Union

import numpy as np

from . import dxf_io as _rs  # type: ignore

if TYPE_CHECKING:
    import pyvista as pv
else:
    try:
        import pyvista as pv

        HAS_PYVISTA = True
    except ImportError:
        pv = None  # type: ignore[assignment]
        HAS_PYVISTA = False


class _RawMesh(NamedTuple):
    """Raw mesh data from Rust parser."""

    points: np.ndarray
    faces: np.ndarray
    labels: np.ndarray


def parse_dxf_fast(dxf_file: str, decimals: int = 5) -> dict[str, Any]:
    """Parse DXF file with fast Rust implementation.

    Args:
        dxf_file: Path to DXF file or DXF content string
        decimals: Decimal places for point rounding

    Returns:
        Dictionary with 'points', 'faces', and 'labels' arrays
    """
    # Check if it's a file path or DXF content
    if dxf_file.startswith("SOLID") or dxf_file.startswith("  0\nSOLID"):
        dxf_content = dxf_file
    else:
        with open(dxf_file, encoding="utf-8") as f:
            dxf_content = f.read()

    rs_raw = _rs.parse_dxf_fast(dxf_content)  # type: ignore[attr-defined]
    points = rs_raw.points_array()  # type: ignore[attr-defined]
    faces = rs_raw.faces_array()  # type: ignore[attr-defined]
    labels = rs_raw.labels_array()  # type: ignore[attr-defined]

    return {
        "points": points.astype(np.float64),
        "faces": faces.astype(np.intp),
        "labels": labels.astype(np.intp),
    }


def write_dxf_fast(points: np.ndarray, faces: np.ndarray, output_file: Optional[str] = None) -> str:
    """Write mesh to DXF format.

    Args:
        points: Nx3 array of vertex coordinates
        faces: Mx3 array of face indices
        output_file: Optional output file path

    Returns:
        DXF content as string
    """
    dxf_content = _rs.write_dxf_fast(  # type: ignore[attr-defined]
        points.tolist(), faces.tolist()
    )

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(dxf_content)

    return dxf_content


def _extract_component(
    component_mask: np.ndarray,
    points: np.ndarray,
    faces: np.ndarray,
    attributes: Optional[dict[str, Any]] = None,
) -> Union[dict[str, Any], "pv.PolyData"]:  # type: ignore[name-defined]
    """Extract a single component as mesh.

    Args:
        component_mask: Boolean mask for component vertices
        points: All vertices
        faces: All faces
        attributes: Optional mesh attributes

    Returns:
        PyVista PolyData if available, else dict
    """
    component_points = points[component_mask]
    vertex_map = {old_idx: new_idx for new_idx, old_idx in enumerate(np.where(component_mask)[0])}

    component_faces = []
    for face in faces:
        if all(vertex in vertex_map for vertex in face):
            component_faces.append([vertex_map[v] for v in face])

    mesh_data = {
        "points": component_points,
        "faces": np.array(component_faces, dtype=np.intp),
    }

    if attributes:
        mesh_data["attributes"] = attributes  # type: ignore[assignment]

    if not HAS_PYVISTA:
        return mesh_data

    poly = pv.PolyData()  # type: ignore[union-attr]
    poly.points = component_points

    # Set faces in VTK format
    pv_faces = np.hstack((np.full((len(component_faces), 1), 3), np.array(component_faces)))
    poly.faces = pv_faces.ravel()

    if attributes:
        for attr_name, attr_data in attributes.items():  # type: ignore[union-attr]
            if isinstance(attr_data, dict):
                poly.cell_data[attr_name] = attr_data.get("data", [])  # type: ignore[index]
            else:
                poly.cell_data[attr_name] = attr_data  # type: ignore[index]

    return poly


def diagnose_mesh(mesh: Union[dict[str, Any], "pv.PolyData"]) -> dict[str, Any]:  # type: ignore[name-defined]
    """Diagnose mesh quality.

    Args:
        mesh: Mesh as dict or PyVista PolyData

    Returns:
        Diagnostic information
    """
    if isinstance(mesh, dict):
        points = mesh["points"]
        faces = mesh["faces"]
    else:
        points = mesh.points  # type: ignore[attr-defined]
        faces = mesh.faces.reshape(-1, 4)[:, 1:4]  # type: ignore[attr-defined]

    return {
        "n_points": len(points),
        "n_faces": len(faces),
        "bounds": {
            "x": (float(points[:, 0].min()), float(points[:, 0].max())),
            "y": (float(points[:, 1].min()), float(points[:, 1].max())),
            "z": (float(points[:, 2].min()), float(points[:, 2].max())),
        },
    }


def to_manifold3d(mesh: "pv.PolyData") -> Any:  # type: ignore[name-defined]
    """Convert mesh to Manifold3D.

    Args:
        mesh: PyVista PolyData

    Returns:
        Manifold3D mesh object
    """
    if not HAS_PYVISTA:
        raise ImportError("PyVista required for manifold operations")

    try:
        import manifold3d  # type: ignore[import-not-found]
    except ImportError as e:
        raise ImportError("manifold3d required for this operation") from e

    points = mesh.points  # type: ignore[attr-defined]
    faces = mesh.faces.reshape(-1, 4)[:, 1:4]  # type: ignore[attr-defined]

    return manifold3d.Mesh(points, faces)  # type: ignore[attr-defined]


def from_manifold3d(m: Any) -> "pv.PolyData":  # type: ignore[name-defined]
    """Convert Manifold3D mesh to PyVista.

    Args:
        m: Manifold3D mesh object

    Returns:
        PyVista PolyData
    """
    if not HAS_PYVISTA:
        raise ImportError("PyVista required")

    f = m.GetTriVerts()  # type: ignore[attr-defined]
    return pv.PolyData(m.vert_properties[:, :3], f.ravel())  # type: ignore[union-attr]


class MeshWithAttributes:
    """Mesh with optional cell and point data attributes."""

    def __init__(
        self,
        points: np.ndarray,
        faces: np.ndarray,
        labels: Optional[np.ndarray] = None,
        point_data: Optional[dict[str, np.ndarray]] = None,
        cell_data: Optional[dict[str, np.ndarray]] = None,
    ) -> None:
        """Initialize mesh.

        Args:
            points: Nx3 vertex coordinates
            faces: Mx3 face indices
            labels: Component labels for each vertex
            point_data: Optional point attributes
            cell_data: Optional cell/face attributes
        """
        self.points = points
        self.faces = faces
        self.labels = labels if labels is not None else np.zeros(len(points), dtype=np.intp)
        self.point_data = point_data or {}
        self.cell_data = cell_data or {}

    @property
    def n_points(self) -> int:
        """Number of vertices."""
        return len(self.points)

    @property
    def n_faces(self) -> int:
        """Number of faces."""
        return len(self.faces)

    @property
    def n_components(self) -> int:
        """Number of connected components."""
        return int(np.max(self.labels)) + 1

    def to_dxf(self, output_file: Optional[str] = None) -> str:
        """Export to DXF format.

        Args:
            output_file: Optional output file path

        Returns:
            DXF content as string
        """
        return write_dxf_fast(self.points, self.faces, output_file)

    def to_pyvista(self) -> "pv.PolyData":  # type: ignore[name-defined]
        """Convert to PyVista PolyData.

        Returns:
            PyVista mesh
        """
        if not HAS_PYVISTA:
            raise ImportError("PyVista required for conversion")

        poly = pv.PolyData(self.points, np.hstack((np.full((len(self.faces), 1), 3), self.faces)))  # type: ignore[union-attr]

        # Add attributes
        for name, data in self.point_data.items():
            poly.point_data[name] = data  # type: ignore[index]

        for name, data in self.cell_data.items():
            poly.cell_data[name] = data  # type: ignore[index]

        return poly


def dxf_to_manifold_meshes(
    dxf_file: str,
    use_pyvista: bool = True,
    with_attributes: bool = True,
) -> list[Union[MeshWithAttributes, "pv.PolyData"]]:  # type: ignore[name-defined]
    """Parse DXF file and extract connected component meshes.

    Args:
        dxf_file: Path to DXF file or DXF content string
        use_pyvista: Return PyVista PolyData if available
        with_attributes: Include attributes in output

    Returns:
        List of meshes (one per connected component)
    """
    mesh_data = parse_dxf_fast(dxf_file)
    points = mesh_data["points"]
    faces = mesh_data["faces"]
    labels = mesh_data["labels"]

    meshes = []
    for component_id in range(labels.max() + 1):
        component_mask = labels == component_id
        attributes = None if not with_attributes else {}

        mesh = _extract_component(component_mask, points, faces, attributes)

        # Convert to MeshWithAttributes if needed
        if isinstance(mesh, dict):
            mesh_obj = MeshWithAttributes(
                mesh["points"],
                mesh["faces"],
                labels[component_mask],
                point_data=mesh.get("attributes", {}),  # type: ignore[arg-type]
            )
            if HAS_PYVISTA and use_pyvista:
                meshes.append(mesh_obj.to_pyvista())
            else:
                meshes.append(mesh_obj)
        else:
            meshes.append(mesh)

    return meshes


__all__ = [
    "dxf_to_manifold_meshes",
    "parse_dxf_fast",
    "write_dxf_fast",
    "MeshWithAttributes",
    "diagnose_mesh",
]
