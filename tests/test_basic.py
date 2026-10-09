"""Tests for dxf_io."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from dxf_io import (
    MeshWithAttributes,
    diagnose_mesh,
    dxf_to_manifold_meshes,
    parse_dxf_fast,
    write_dxf_fast,
)


def _entity(name: str, corners: list[tuple[float, float, float]]) -> str:
    out = f"  0\n{name}\n  8\n0\n"
    for i, (x, y, z) in enumerate(corners):
        out += f" {10 + i}\n{x}\n {20 + i}\n{y}\n {30 + i}\n{z}\n"
    return out


def _dxf(*entities: str) -> str:
    return "  0\nSECTION\n  2\nENTITIES\n" + "".join(entities) + "  0\nENDSEC\n  0\nEOF\n"


# A unit square split in two triangles (3DFACE, perimeter order) ...
SQUARE = _entity("3DFACE", [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)])
# ... and a separate triangle (SOLID triangle: 4th corner equals the 3rd).
TRIANGLE = _entity("SOLID", [(5, 5, 5), (6, 5, 5), (5, 6, 5), (5, 6, 5)])
# A SOLID quad: corners are stored in zig-zag order (0, 1, 3, 2 around the perimeter).
SOLID_QUAD = _entity("SOLID", [(0, 0, 2), (1, 0, 2), (0, 1, 2), (1, 1, 2)])

TWO_PARTS = _dxf(SQUARE, TRIANGLE)


class TestParsing:
    def test_quad_is_split_and_vertices_merged(self) -> None:
        mesh = parse_dxf_fast(_dxf(SQUARE))
        assert mesh["points"].shape == (4, 3)
        assert mesh["faces"].shape == (2, 3)
        assert mesh["labels"].tolist() == [0, 0, 0, 0]

    def test_triangle_solid(self) -> None:
        mesh = parse_dxf_fast(_dxf(TRIANGLE))
        assert mesh["points"].shape == (3, 3)
        assert mesh["faces"].shape == (1, 3)

    def test_solid_zigzag_order(self) -> None:
        mesh = parse_dxf_fast(_dxf(SOLID_QUAD))
        pts = mesh["points"]
        # Both triangles must lie on the perimeter quad (0,0)-(1,0)-(1,1)-(0,1):
        # neither may use the (0,1)-(1,0) diagonal... both do share a diagonal, but
        # the area covered must be the full unit square.
        area = 0.0
        for a, b, c in mesh["faces"]:
            area += 0.5 * abs(np.cross(pts[b] - pts[a], pts[c] - pts[a])[2])
        assert area == pytest.approx(1.0)

    def test_two_components(self) -> None:
        mesh = parse_dxf_fast(TWO_PARTS)
        assert mesh["points"].shape == (7, 3)
        assert sorted(set(mesh["labels"].tolist())) == [0, 1]

    def test_decimals_controls_merging(self) -> None:
        near = _dxf(
            _entity("3DFACE", [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 1, 0)]),
            _entity("3DFACE", [(1.0000001, 0, 0), (1, 1, 0), (0, 1, 0), (0, 1, 0)]),
        )
        assert len(parse_dxf_fast(near, decimals=3)["points"]) == 4
        assert len(parse_dxf_fast(near, decimals=9)["points"]) == 5

    def test_ignores_other_entities_and_garbage(self) -> None:
        text = "  0\nLINE\n 10\n9\n 20\n9\n 30\n9\n" + SQUARE + "not a number\nx\n"
        assert parse_dxf_fast(_dxf(text))["faces"].shape == (2, 3)

    def test_empty(self) -> None:
        mesh = parse_dxf_fast(_dxf())
        assert mesh["points"].shape == (0, 3)
        assert mesh["faces"].shape == (0, 3)
        assert len(mesh["labels"]) == 0

    def test_parse_file(self, tmp_path: Path) -> None:
        path = tmp_path / "test.dxf"
        path.write_text(TWO_PARTS, encoding="utf-8")
        assert len(parse_dxf_fast(path)["faces"]) == 3
        assert len(parse_dxf_fast(str(path))["faces"]) == 3

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            parse_dxf_fast(tmp_path / "missing.dxf")


class TestComponents:
    def test_split(self) -> None:
        meshes = dxf_to_manifold_meshes(TWO_PARTS, use_pyvista=False)
        assert [type(m) for m in meshes] == [MeshWithAttributes] * 2
        assert sorted(m.n_faces for m in meshes) == [1, 2]
        for m in meshes:
            assert m.faces.max() < m.n_points
            assert m.n_components == 1

    def test_diagnose(self) -> None:
        mesh = dxf_to_manifold_meshes(_dxf(SQUARE), use_pyvista=False)[0]
        info = diagnose_mesh(mesh)
        assert info["n_points"] == 4
        assert info["n_faces"] == 2
        assert info["bounds"]["x"] == (0.0, 1.0)

    def test_empty_mesh_properties(self) -> None:
        mesh = MeshWithAttributes(np.zeros((0, 3)), np.zeros((0, 3), dtype=int))
        assert (mesh.n_points, mesh.n_faces, mesh.n_components) == (0, 0, 0)


class TestWriting:
    def test_write_contains_3dface(self) -> None:
        mesh = parse_dxf_fast(_dxf(SQUARE))
        text = write_dxf_fast(mesh["points"], mesh["faces"])
        assert text.count("3DFACE") == 2
        assert "ENTITIES" in text
        assert text.rstrip().endswith("EOF")

    def test_roundtrip(self, tmp_path: Path) -> None:
        original = parse_dxf_fast(TWO_PARTS)
        out = tmp_path / "out.dxf"
        write_dxf_fast(original["points"], original["faces"], out)
        again = parse_dxf_fast(out)
        assert again["points"].shape == original["points"].shape
        assert again["faces"].shape == original["faces"].shape
        assert sorted(map(tuple, again["points"].round(6).tolist())) == sorted(
            map(tuple, original["points"].round(6).tolist())
        )

    def test_mesh_to_dxf(self, tmp_path: Path) -> None:
        data = parse_dxf_fast(_dxf(SQUARE))
        mesh = MeshWithAttributes(data["points"], data["faces"])
        out = tmp_path / "m.dxf"
        text = mesh.to_dxf(out)
        assert out.read_text(encoding="utf-8") == text


def test_pyvista_optional() -> None:
    pv = pytest.importorskip("pyvista")
    (poly,) = dxf_to_manifold_meshes(_dxf(SQUARE), use_pyvista=True)
    assert isinstance(poly, pv.PolyData)
    assert poly.n_cells == 2
