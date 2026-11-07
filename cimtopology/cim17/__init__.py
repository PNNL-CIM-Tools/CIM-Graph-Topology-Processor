"""CIM17 topology processor (cimhub_2023 / cim17v40 profiles), frozen as the behavioral reference.

This is the pre-CIM18 code, unchanged apart from import paths and two cim-graph 0.6
compatibility fixes in ``distribution/distributed_topology.py::check_boundary``.
``test/cim17`` pins what it produces; the CIM18 rewrite (``cimtopology.cim18``) is checked
against it. Do not refactor or "simplify" logic here: the transformer-end voltage ladder in
``check_boundary`` *is* the definition of a secondary area.
"""
