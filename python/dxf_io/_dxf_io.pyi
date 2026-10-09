"""Type stubs for the compiled Rust extension ``dxf_io._dxf_io``."""

import os

import numpy as np
import numpy.typing as npt

def parse_dxf_bytes(
    data: bytes, decimals: int = 6
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.int64], npt.NDArray[np.int64]]: ...
def parse_dxf_file(
    path: str | os.PathLike[str], decimals: int = 6
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.int64], npt.NDArray[np.int64]]: ...
def write_dxf_string(points: npt.NDArray[np.float64], faces: npt.NDArray[np.int64]) -> str: ...
def write_dxf_file(
    path: str | os.PathLike[str], points: npt.NDArray[np.float64], faces: npt.NDArray[np.int64]
) -> None: ...
