"""The single entry point for building CIM topology: TopologicalNodes and Islands."""
from __future__ import annotations

import logging

from cimgraph.models import GraphModel

from cimtopology.distribution.bus_topology import build_bus_topology
from cimtopology.distribution.feeder_island import build_feeder_islands

_log = logging.getLogger(__name__)


def build_topology(network: GraphModel, *, xfmr_boundary: bool = False) -> None:
    """Build the network's TopologicalNodes and TopologicalIslands in place.

    Two derived layers, in order, because the second is built from the first:

    1. ``TopologicalNode`` -- one per bus, merging the ConnectivityNodes that are the
       same electrical point. Crosses tank-modelled transformers, which is what makes
       this work on real distribution models.
    2. ``TopologicalIsland`` -- one per set of nodes that are energized together,
       which is where switch state matters.

    The split is why the two questions get different answers about a switch: an open
    switch does not divide a bus (layer 1 ignores switch state), but it does divide an
    island (layer 2 respects it).

    Args:
        network: A live cimgraph GraphModel, mutated in place.
        xfmr_boundary: Treat transformers as bus boundaries, giving the
            per-voltage-level buses a power-flow solver needs. The default False
            merges through them, which is what island detection wants.

    Safe to call repeatedly: existing nodes and islands are deleted before
    rebuilding, so a second call on the same model reproduces the first.

    A one-node bus or a one-node island is a legitimate result, not an error -- it
    means a ConnectivityNode that nothing bridges onward. Callers classify those
    downstream (a lone node carrying dangling equipment is a "floating node").
    """
    nodes = build_bus_topology(network, xfmr_boundary=xfmr_boundary)
    islands = build_feeder_islands(network)

    _log.info(f'Topology complete: {len(nodes)} TopologicalNode(s), '
              f'{len(islands)} TopologicalIsland(s)')
