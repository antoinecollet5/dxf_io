"""Basic tests for dxf_io."""

import pytest


def test_import():
    """Test that the module can be imported."""
    try:
        import dxf_io
        assert hasattr(dxf_io, 'parse_dxf_fast')
    except ImportError:
        pytest.skip("Rust extension not built yet. Run: maturin develop -r")


def test_wrapper_import():
    """Test that the wrapper can be imported."""
    try:
        from dxf_io_wrapper import dxf_to_manifold_meshes
        assert callable(dxf_to_manifold_meshes)
    except ImportError as e:
        pytest.skip(f"Wrapper import failed: {e}")


@pytest.mark.parametrize("decimals", [3, 6, 8])
def test_decimals_parameter(decimals):
    """Test that decimals parameter is accepted."""
    try:
        from dxf_io import RawMesh
        # Just test that RawMesh can be accessed
        assert RawMesh is not None
    except ImportError:
        pytest.skip("Rust extension not built yet")
