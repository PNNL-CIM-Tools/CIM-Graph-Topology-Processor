"""``build_topology``: the TopologicalNodes and TopologicalIslands of a cim18v17 model, in place.

The cim18v17 successor of the cimhub_2026-era ``cimtopology.build_topology(network, xfmr_boundary=False)``
that CIM-Repair calls. There is no ``xfmr_boundary``: a bus never spans a transformer (IEC 61970-301),
and an island always crosses one.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from cimtopology.cim18.topological_island import build_topological_islands
from cimtopology.cim18.topological_node import build_topological_nodes

if TYPE_CHECKING:
    from cimgraph.models import GraphModel


def build_topology(model: GraphModel) -> None:
    """Rebuild the model's buses, then its islands. Safe to run again after switching."""
    build_topological_nodes(model)
    build_topological_islands(model)
