.. _installation_ref:

============
Installation
============

Stable release
--------------

To install dxf_io, run this command in your terminal:

.. code-block:: console

    $ pip install dxf_io

Optional dependencies add the conversions to other libraries:

.. code-block:: console

    $ pip install "dxf_io[visualization]"   # PyVista
    $ pip install "dxf_io[manifold]"        # manifold3d
    $ pip install "dxf_io[all]"             # both

Pre-built wheels are available for Linux (x86_64 and aarch64, glibc and musl), macOS
(Intel and Apple Silicon) and Windows (x64 and ARM64), for CPython 3.10 to 3.15,
including the free-threaded builds. Nothing needs to be compiled.

If you don't have `pip`_ installed, this `Python installation guide`_ can guide
you through the process.

.. _pip: https://pip.pypa.io
.. _Python installation guide: https://docs.python-guide.org/starting/installation/

From sources
------------

The sources for dxf_io can be downloaded from the `GitHub repo`_. Building them
requires a `Rust toolchain <https://rustup.rs>`_ (1.88 or newer).

.. code-block:: console

    $ git clone https://github.com/antoinecollet5/dxf_io
    $ cd dxf_io
    $ pip install .

For development, `uv <https://docs.astral.sh/uv/>`_ builds the extension and installs
the development tools in one step:

.. code-block:: console

    $ uv sync   # also rebuilds the extension after changes to the Rust code

See :doc:`contributing` for more details.

Next steps
----------

For a quick overview of dxf_io functionality, see the :ref:`user guide<user_guide_ref>`.
You can also refer to the :ref:`API reference<api_ref>` for an exhaustive list of what
is available.

.. _GitHub repo: https://github.com/antoinecollet5/dxf_io
