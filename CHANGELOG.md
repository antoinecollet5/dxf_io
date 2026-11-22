# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.0] - Unreleased

First public release.

### Added
- Parallel, GIL-free parsing of `SOLID` / `3DFACE` entities of ASCII DXF files
  (`parse_dxf_fast`), with vertex merging and connected-component labelling.
- Parallel DXF writer (`write_dxf_fast`, `MeshWithAttributes.to_dxf`), to a string or
  streamed to a file.
- `dxf_to_manifold_meshes` to split a file into its connected components, as
  `MeshWithAttributes` or `pyvista.PolyData` objects.
- Conversion to and from `manifold3d`.
- Wheels for Linux, macOS and Windows (x86_64 and ARM64), CPython 3.10 to 3.15,
  including free-threaded builds.
