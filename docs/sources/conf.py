"""Sphinx configuration for the dxf_io documentation.

The package is imported from ``python/`` and its compiled Rust extension is mocked, so
building the documentation needs neither a Rust toolchain nor an installed dxf_io.
"""

import datetime
import os
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

# -- Project information -------------------------------------------------------

project = "dxf_io"
author = "Antoine Collet"
copyright = f"2026-{datetime.date.today().year}, {author}"
# The version lives in Cargo.toml (see CONTRIBUTING.md).
with open(ROOT / "Cargo.toml", "rb") as f:
    release = tomllib.load(f)["package"]["version"]
version = ".".join(release.split(".")[:2])

# -- General configuration -----------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",  # API documentation from docstrings
    "sphinx.ext.autosummary",  # summary tables and one page per object
    "sphinx.ext.napoleon",  # NumPy-style docstrings
    "sphinx.ext.doctest",  # test snippets in the documentation
    "sphinx.ext.viewcode",  # links to the highlighted source code
    "sphinx.ext.intersphinx",  # links to other projects' documentation
    "sphinx_copybutton",  # "copy" button on code blocks
    "myst_parser",  # Markdown pages (CONTRIBUTING.md, CHANGELOG.md)
]

templates_path = ["_templates"]
exclude_patterns = ["build", "Thumbs.db", ".DS_Store", "__pycache__"]
source_suffix = {".rst": "restructuredtext", ".md": "markdown"}
root_doc = "index"
pygments_style = "sphinx"

# -- Autodoc / autosummary -----------------------------------------------------

autosummary_generate = True
autoclass_content = "class"  # the __init__ docstring is shown by the class template
autodoc_member_order = "groupwise"
# Types are documented in the NumPy-style docstrings; "none" also gives one clean
# signature for functions with typing overloads (write_dxf_fast, to_dxf).
autodoc_typehints = "none"
# The Rust extension is not compiled when building the documentation.
autodoc_mock_imports = ["dxf_io._dxf_io"]

napoleon_google_docstring = False
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = False
napoleon_use_ivar = True

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "numpy": ("https://numpy.org/doc/stable/", None),
    "pyvista": ("https://docs.pyvista.org/", None),
}
# Offline builds (DXF_IO_DOCS_OFFLINE=1): skip the inventories of the other projects,
# whose download would fail and, with -W, stop the build.
if os.environ.get("DXF_IO_DOCS_OFFLINE"):
    intersphinx_mapping = {}

# -- HTML output ---------------------------------------------------------------

html_theme = "pydata_sphinx_theme"
html_title = f"dxf_io {release}"
html_theme_options = {
    "show_prev_next": False,
    "github_url": "https://github.com/antoinecollet5/dxf_io",
    "icon_links": [
        {
            "name": "PyPI",
            "url": "https://pypi.org/project/dxf_io/",
            "icon": "fa-brands fa-python",
        },
        {
            "name": "Support",
            "url": "https://github.com/antoinecollet5/dxf_io/issues",
            "icon": "fa-solid fa-comment",
        },
    ],
}
html_static_path: list[str] = []
html_copy_source = False
htmlhelp_basename = "dxf_iodoc"

# -- LaTeX / man pages ---------------------------------------------------------

latex_documents = [(root_doc, "dxf_io.tex", "dxf_io Documentation", author, "manual")]
man_pages = [(root_doc, "dxf_io", "dxf_io Documentation", [author], 1)]
