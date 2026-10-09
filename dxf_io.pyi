"""Type stubs for dxf_io Rust extension."""

from typing import Any

import numpy as np
import numpy.typing as npt

class RawMesh:
    """Raw mesh from Rust parser."""

    points: list[list[float]]
    faces: list[list[int]]
    labels: list[int]

    def __init__(
        self,
        points: list[list[float]],
        faces: list[list[int]],
        labels: list[int],
    ) -> None: ...

    @property
    def n_points(self) -> int: ...

    @property
    def n_faces(self) -> int: ...

    @property
    def n_components(self) -> int: ...

    def points_array(self) -> npt.NDArray[np.float64]: ...

    def faces_array(self) -> npt.NDArray[np.intp]: ...

    def labels_array(self) -> npt.NDArray[np.intp]: ...

    def to_dxf(self) -> str: ...

def parse_dxf_fast(content: str) -> RawMesh: ...

def write_dxf_fast(points: list[list[float]], faces: list[list[int]]) -> str: ...
