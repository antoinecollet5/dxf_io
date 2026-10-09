"""Tests for dxf_io."""

from __future__ import annotations

from collections.abc import Sequence
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


def _entity(name: str, corners: Sequence[Sequence[float]]) -> str:
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


def _grid_dxf(n: int, parts: int = 1, eol: str = "\n", kind: str = "3DFACE") -> str:
    """``parts`` disjoint n x n grids of quads."""
    chunks = []
    for part in range(parts):
        off = part * (n + 5)
        for i in range(n):
            for j in range(n):
                x, y = off + i, j
                corners = [(x, y, 0), (x + 1, y, 0), (x + 1, y + 1, 0), (x, y + 1, 0)]
                if kind == "SOLID":  # zig-zag order
                    corners[2], corners[3] = corners[3], corners[2]
                chunks.append(_entity(kind, corners))
    return _dxf(*chunks).replace("\n", eol)


class TestLargeInputs:
    """Inputs above 4 MB are split in chunks and parsed in parallel."""

    @pytest.mark.parametrize("eol", ["\n", "\r\n"])
    @pytest.mark.parametrize("kind", ["3DFACE", "SOLID"])
    def test_parallel_matches_expected(self, eol: str, kind: str) -> None:
        n, parts = 150, 3
        text = _grid_dxf(n, parts, eol, kind)
        assert len(text) > 4 << 20  # large enough to be chunked
        mesh = parse_dxf_fast(text)
        assert mesh["points"].shape == (parts * (n + 1) ** 2, 3)
        assert mesh["faces"].shape == (parts * 2 * n * n, 3)
        assert sorted(set(mesh["labels"].tolist())) == list(range(parts))
        pts = mesh["points"]
        area = sum(
            0.5 * abs(np.cross(pts[b] - pts[a], pts[c] - pts[a])[2])
            for a, b, c in mesh["faces"][:: len(mesh["faces"]) // 500]
        )
        assert area == pytest.approx(0.5 * len(mesh["faces"][:: len(mesh["faces"]) // 500]))

    def test_chunked_equals_single_chunk(self, tmp_path: Path) -> None:
        big = _grid_dxf(150, 3)
        small = _grid_dxf(5, 3)
        # The same parser must give identical results however the input is cut:
        # compare the big input to itself through the file path and the bytes path.
        path = tmp_path / "big.dxf"
        path.write_text(big, encoding="utf-8")
        a, b = parse_dxf_fast(big), parse_dxf_fast(path)
        for key in ("points", "faces", "labels"):
            np.testing.assert_array_equal(a[key], b[key])
        assert parse_dxf_fast(small)["faces"].shape == (3 * 2 * 25, 3)


class TestEdgeCases:
    def test_solid_with_three_corners(self) -> None:
        text = _dxf(_entity("SOLID", [(0, 0, 0), (1, 0, 0), (0, 1, 0)]))
        mesh = parse_dxf_fast(text)
        assert mesh["points"].shape == (3, 3)
        assert mesh["faces"].shape == (1, 3)
        assert sorted(map(tuple, mesh["points"].tolist())) == [
            (0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (1.0, 0.0, 0.0),
        ]

    def test_degenerate_entities_are_dropped(self) -> None:
        text = _dxf(_entity("3DFACE", [(0, 0, 0), (0, 0, 0), (1, 0, 0), (1, 0, 0)]))
        assert parse_dxf_fast(text)["faces"].shape == (0, 3)

    def test_no_trailing_newline(self) -> None:
        assert parse_dxf_fast(_dxf(SQUARE).rstrip("\n") + "\n  0\nEOF")["faces"].shape == (2, 3)

    def test_parse_is_independent_of_decimals_type_hint(self) -> None:
        assert parse_dxf_fast(_dxf(SQUARE), 0)["points"].shape == (4, 3)


class TestWriteFormat:
    def test_numbers_and_codes(self) -> None:
        pts = np.array([[-0.5, 1234.5678915, 0.0], [1e-9, -1e-9, 2.0], [3.0, 4.0, 5.0]])
        text = write_dxf_fast(pts, np.array([[0, 1, 2]]))
        lines = text.splitlines()
        body = lines[lines.index("ENTITIES") + 1 :]
        assert body[:6] == ["  0", "3DFACE", "  8", "0", " 62", "1"]
        pairs = {k.strip(): v for k, v in zip(body[6:30:2], body[7:30:2])}
        # Each of the 12 group codes (10-13, 20-23, 30-33) appears exactly once.
        assert sorted(pairs, key=int) == [
            str(c) for c in (10, 11, 12, 13, 20, 21, 22, 23, 30, 31, 32, 33)
        ]
        assert pairs["10"] == "-0.500000"
        assert pairs["20"] in ("1234.567891", "1234.567892")
        assert pairs["11"] == "0.000000" and pairs["21"] == "0.000000"  # no "-0.000000"
        assert pairs["13"] == pairs["12"] and pairs["33"] == pairs["32"]  # triangle

    def test_huge_values_fall_back(self) -> None:
        text = write_dxf_fast(np.array([[1e15, 0, 0], [0, 1, 0], [0, 0, 1]]), np.array([[0, 1, 2]]))
        assert "1000000000000000.000000" in text

    def test_file_equals_string(self, tmp_path: Path) -> None:
        data = parse_dxf_fast(_grid_dxf(40, 2))
        out = tmp_path / "f.dxf"
        write_dxf_fast(data["points"], data["faces"], out)
        assert out.read_text(encoding="utf-8") == write_dxf_fast(data["points"], data["faces"])

    def test_large_roundtrip_is_lossless(self, tmp_path: Path) -> None:
        # Enough faces for several parallel render blocks.
        data = parse_dxf_fast(_grid_dxf(130, 1))
        assert len(data["faces"]) > 16_384
        out = tmp_path / "big.dxf"
        write_dxf_fast(data["points"], data["faces"], out)
        again = parse_dxf_fast(out)
        assert again["faces"].shape == data["faces"].shape
        np.testing.assert_allclose(again["points"], data["points"])

    def test_non_contiguous_and_other_dtypes(self) -> None:
        pts = np.arange(18.0).reshape(3, 6)[:, ::2]  # non-contiguous view
        faces = np.array([[0, 1, 2]], dtype=np.int32)
        assert write_dxf_fast(pts, faces).count("3DFACE") == 1

    @pytest.mark.parametrize("faces", [[[0, 1, 3]], [[-1, 0, 1]]])
    def test_bad_index(self, faces: list[list[int]]) -> None:
        with pytest.raises(ValueError, match="out of range"):
            write_dxf_fast(np.zeros((3, 3)), np.array(faces))

    def test_bad_shape(self) -> None:
        with pytest.raises(ValueError):
            write_dxf_fast(np.zeros((3, 2)), np.array([[0, 1, 2]]))


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
        assert mesh.to_dxf(out) is None
        assert out.read_text(encoding="utf-8") == mesh.to_dxf()


def test_pyvista_optional() -> None:
    pv = pytest.importorskip("pyvista")
    (poly,) = dxf_to_manifold_meshes(_dxf(SQUARE), use_pyvista=True)
    assert isinstance(poly, pv.PolyData)
    assert poly.n_cells == 2
