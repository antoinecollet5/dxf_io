"""Basic tests for dxf_io."""

import tempfile
from pathlib import Path

import pytest

from dxf_io import MeshWithAttributes, dxf_to_manifold_meshes, parse_dxf_fast

SIMPLE_DXF = """SOLID
10
0.0
20
0.0
30
0.0
10
1.0
20
0.0
30
0.0
10
0.0
20
1.0
30
0.0
ENDSOL
"""


class TestParsing:
    """Test DXF parsing."""

    def test_parse_simple(self) -> None:
        """Test parsing simple DXF."""
        result = parse_dxf_fast(SIMPLE_DXF)
        assert result.points
        assert result.faces
        assert result.labels
        assert len(result.points) > 0
        assert len(result.faces) > 0

    def test_parse_file(self) -> None:
        """Test parsing from file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dxf_path = Path(tmpdir) / "test.dxf"
            dxf_path.write_text(SIMPLE_DXF, encoding="utf-8")
            result = parse_dxf_fast(str(dxf_path))
            assert result.points

    def test_components(self) -> None:
        """Test component extraction."""
        meshes = dxf_to_manifold_meshes(SIMPLE_DXF, use_pyvista=False)
        assert len(meshes) > 0
        assert isinstance(meshes[0], MeshWithAttributes)

    def test_mesh_properties(self) -> None:
        """Test mesh properties."""
        result = parse_dxf_fast(SIMPLE_DXF)
        mesh = MeshWithAttributes(
            result.points,
            result.faces,
            result.labels,
        )
        assert mesh.n_points > 0
        assert mesh.n_faces > 0
        assert mesh.n_components > 0


class TestWriting:
    """Test DXF writing."""

    def test_write_dxf(self) -> None:
        """Test writing DXF."""
        result = parse_dxf_fast(SIMPLE_DXF)
        mesh = MeshWithAttributes(
            result.points,
            result.faces,
            result.labels,
        )
        dxf_output = mesh.to_dxf()
        assert "3DFACE" in dxf_output
        assert "SECTION" in dxf_output

    def test_roundtrip(self) -> None:
        """Test read-write roundtrip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "output.dxf"
            result = parse_dxf_fast(SIMPLE_DXF)
            mesh = MeshWithAttributes(
                result.points,
                result.faces,
                result.labels,
            )
            mesh.to_dxf(str(output_path))
            assert output_path.exists()
            assert output_path.stat().st_size > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
