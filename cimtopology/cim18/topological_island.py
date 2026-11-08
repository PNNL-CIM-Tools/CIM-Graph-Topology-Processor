"""TopologicalIslands: the TopologicalNodes joined through energized equipment.

An island crosses every piece of equipment that is in service and, for a switch, closed
(``switching.energizes``): lines and transformers included, which is what makes it an island and not
a bus. Bus ties always cross, so a TopologicalNode is never split between two islands. Run
``build_topological_nodes`` first.

Each island's angle reference is a node with an EnergySource, else one with a SynchronousMachine. An
island with neither (cut off from every source) has none, and the count of those is logged: they are
the unenergized islands CIM-Repair looks for. Islands are listed largest first.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cimtopology.cim18.index import index_model, label
from cimtopology.cim18.switching import energizes, is_bus_tie
from cimtopology.core.linknet import spanning_forest

if TYPE_CHECKING:
    from cimgraph.models import GraphModel

_log = logging.getLogger(__name__)


def clear_islands(model: GraphModel) -> None:
    """Delete every TopologicalIsland and every reference to one, both sides."""
    cim = model.cim
    for island in list(model.graph.get(cim.TopologicalIsland, {}).values()):
        model.delete(island)
    for bus in model.graph.get(cim.TopologicalNode, {}).values():
        bus.TopologicalIsland = None
        bus.AngleRefTopologicalIsland = None


def build_topological_islands(model: GraphModel) -> list:
    """Replace the model's TopologicalIslands, and return them largest first."""
    cim = model.cim
    clear_islands(model)
    index = index_model(model)
    unassigned = [label(node) for node in index.nodes[1:] if node.TopologicalNode is None]
    if unassigned:
        raise ValueError(f"{len(unassigned)} ConnectivityNodes have no TopologicalNode "
                         f"(run build_topological_nodes first), e.g. {unassigned[:5]}")
    crosses = [False] + [is_bus_tie(equipment, cim) or energizes(equipment, cim)
                         for equipment in index.equipment[1:]]
    forest = spanning_forest(index.linknet, range(1, index.linknet.node_count + 1),
                             crosses=lambda equipment: crosses[equipment])
    groups: dict[int, list] = {}
    for node, root in enumerate(forest.tree_of[1:], start=1):
        buses = groups.setdefault(root, [])
        bus = index.nodes[node].TopologicalNode
        if not any(known is bus for known in buses):
            buses.append(bus)

    islands = []
    for buses in sorted(groups.values(), key=len, reverse=True):
        island = cim.TopologicalIsland(name=f'island_{buses[0].name}')
        island.uuid(mRID=f'island_{buses[0].mRID}')
        for bus in buses:
            bus.TopologicalIsland = island
            island.TopologicalNodes.append(bus)
        reference = _angle_reference(buses, cim)
        if reference is not None:
            reference.AngleRefTopologicalIsland = island
            island.AngleRefTopologicalNode = reference
        model.add_to_graph(island)
        islands.append(island)
    dead = sum(island.AngleRefTopologicalNode is None for island in islands)
    if dead:
        _log.warning(f"{dead} of {len(islands)} TopologicalIslands have no EnergySource or SynchronousMachine")
    return islands


def _angle_reference(buses: list, cim):
    for kind in (cim.EnergySource, cim.SynchronousMachine):
        for bus in buses:
            if any(isinstance(terminal.ConductingEquipment, kind) for terminal in bus.Terminal):
                return bus
    return None
