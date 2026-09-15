"""Build TopologicalNodes from the ConnectivityNodes of a distribution model."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cimgraph.models import GraphModel

if TYPE_CHECKING:
    # Annotations only. The live profile comes from `network.cim` at runtime, so this
    # module works against whichever profile the caller's model was built with.
    import cimgraph.data_profile.cimhub_2026 as cim

_log = logging.getLogger(__name__)


def build_bus_topology(network: GraphModel,
                       xfmr_boundary: bool = False) -> list[cim.TopologicalNode]:
    """Merge the model's ConnectivityNodes into TopologicalNodes.

    A TopologicalNode is one bus: the set of ConnectivityNodes that are the same
    electrical point because only non-boundary equipment separates them. What counts
    as a boundary is the whole question, and it depends on what the caller is doing:

    * ``xfmr_boundary=False`` (default) merges across transformers too, so a node
      spans a whole galvanically-connected region. This is what island detection
      wants -- "what is connected to what" -- and it is the mode the consuming
      stack uses.
    * ``xfmr_boundary=True`` stops at transformers, giving the per-voltage-level
      buses a power-flow solver needs.

    Switch state is deliberately NOT a boundary in either mode: an open switch still
    joins two ConnectivityNodes into one bus for topology purposes. Islanding is a
    separate question answered downstream by ``build_feeder_islands``, which walks
    these nodes and does respect switch state.

    Any pre-existing TopologicalNodes are deleted first, so calling this twice on the
    same model yields the same result as calling it once.

    Returns the created nodes, largest first.
    """
    cim = network.cim

    clear_bus_topology(network)

    connectivity_nodes = network.list_by_class(cim.ConnectivityNode)
    if not connectivity_nodes:
        _log.warning('No ConnectivityNodes in the model; nothing to build nodes from')
        return []

    adjacency = _build_adjacency(network, connectivity_nodes, xfmr_boundary)

    groups = _connected_groups(connectivity_nodes, adjacency)
    groups.sort(key=len, reverse=True)

    nodes = [_create_node(network, members, number)
             for number, members in enumerate(groups, start=1)]

    _log.info(f'Built {len(nodes)} TopologicalNode(s) from '
              f'{len(connectivity_nodes)} ConnectivityNodes '
              f'(largest holds {len(groups[0])})')

    return nodes


def clear_bus_topology(network: GraphModel) -> None:
    """Delete existing TopologicalNodes and null every reference to them.

    Deleting the objects is not enough on its own: the Terminal and ConnectivityNode
    back-references would still point at nodes that are no longer in the graph, and a
    rebuild that reads those stale links would resurrect the old topology. Both sides
    are cleared here so a rebuild starts from connectivity alone.
    """
    cim = network.cim

    for terminal in network.list_by_class(cim.Terminal):
        terminal.TopologicalNode = None

    for connectivity_node in network.list_by_class(cim.ConnectivityNode):
        connectivity_node.TopologicalNode = None

    stale = network.list_by_class(cim.TopologicalNode)
    for node in stale:
        network.delete(node)

    if stale:
        _log.debug(f'Cleared {len(stale)} pre-existing TopologicalNode(s)')



def _build_adjacency(network: GraphModel, connectivity_nodes: list,
                     xfmr_boundary: bool) -> dict:
    """Map each ConnectivityNode identifier to those sharing a bus with it.

    Two ConnectivityNodes are adjacent when one piece of *zero-impedance* equipment
    has a terminal on each: the two-hop walk ConnectivityNode -> Terminal ->
    equipment -> Terminal -> ConnectivityNode.
    """
    cim = network.cim

    adjacency = {node.identifier: set() for node in connectivity_nodes}

    for connectivity_node in connectivity_nodes:
        identifier = connectivity_node.identifier

        for terminal in connectivity_node.Terminals:
            equipment = bridging_equipment(terminal)
            if equipment is None:
                continue

            # Only zero-impedance equipment merges ConnectivityNodes into one bus. A
            # switch's two ends are the same electrical point whatever its open/closed
            # state, so it merges; an ACLineSegment has impedance and its ends are
            # genuinely different buses. Bridging lines collapsed the ieee13 fixture's
            # 22 buses into 1 when this test was missing.
            #
            # `isinstance` on the Switch base is deliberate and is NOT the opt-in
            # `get_switch_classes` rule: an area boundary must be something an ADMS can
            # operate, but merging asks only about impedance, and every Switch subclass
            # has none -- a fuse, disconnector, earthing switch, jumper or cut joins its
            # two points exactly as a breaker does.
            #
            # A transformer is the caller's choice: its windings are separate buses for
            # power flow (xfmr_boundary=True), merged when asking what is galvanically
            # connected (the default).
            if isinstance(equipment, cim.PowerTransformer):
                if xfmr_boundary:
                    continue
            elif not isinstance(equipment, (cim.Switch, cim.BusbarSection)):
                continue

            for other in equipment_terminals(equipment):
                other_node = other.ConnectivityNode
                if other_node is None:
                    continue
                other_id = other_node.identifier
                # A neighbour reached through equipment can lie outside this model
                # (the far side of a boundary in a distributed sub-model). It cannot
                # join a bus we are building, so bridge only nodes we actually hold.
                if other_id != identifier and other_id in adjacency:
                    adjacency[identifier].add(other_id)
                    adjacency[other_id].add(identifier)

    return adjacency


def bridging_equipment(terminal: cim.Terminal) -> cim.Equipment | None:
    """The equipment a Terminal belongs to, resolving tank-transformer terminals.

    An ordinary terminal points at its equipment through ``ConductingEquipment``. A
    tank winding's terminal does not: a TransformerTank is Equipment rather than
    ConductingEquipment, so the terminal carries ``ConductingEquipment is None`` and
    is wired instead via ``Terminal.TransformerEnd -> TransformerTank ->
    PowerTransformer``.

    Without this hop a traversal cannot cross a tank-modelled transformer, and
    distribution models are full of them -- typically all but a couple of a feeder's
    transformers are
    tank-modelled -- so every one would shatter the feeder into false islands.
    """
    equipment = terminal.ConductingEquipment
    if equipment is not None:
        return equipment

    for end in terminal.TransformerEnd:
        tank = getattr(end, 'TransformerTank', None)
        if tank is not None:
            return tank.PowerTransformer

    return None


def equipment_terminals(equipment: cim.Equipment) -> list[cim.Terminal]:
    """Every Terminal of a piece of equipment, including a tank transformer's.

    A tank-modelled PowerTransformer carries nothing on ``.Terminals``; each
    winding's terminal lives at ``TransformerTanks[].TransformerTankEnds[].Terminal``.
    Collecting both is what makes the two ends of a transformer count as one piece
    of equipment, which is the property that bridges its nodes.
    """
    terminals = list(equipment.Terminals)

    for tank in getattr(equipment, 'TransformerTanks', None) or []:
        for tank_end in tank.TransformerTankEnds:
            if tank_end.Terminal is not None:
                terminals.append(tank_end.Terminal)

    return terminals


def _connected_groups(connectivity_nodes: list, adjacency: dict) -> list[list]:
    """Partition ConnectivityNodes into mutually reachable groups."""
    by_id = {node.identifier: node for node in connectivity_nodes}
    unassigned = dict(by_id)

    groups = []
    while unassigned:
        # Popping the seed is what makes this loop terminate.
        seed = unassigned.pop(next(iter(unassigned)))
        members = [seed]
        queue = [seed]

        while queue:
            current = queue.pop(0)
            for neighbour_id in adjacency.get(current.identifier, ()):
                neighbour = unassigned.pop(neighbour_id, None)
                if neighbour is not None:
                    members.append(neighbour)
                    queue.append(neighbour)

        groups.append(members)

    return groups


def _create_node(network: GraphModel, members: list,
                 number: int) -> cim.TopologicalNode:
    """Create one TopologicalNode over a group of ConnectivityNodes.

    Both directions of both associations are written. That is not redundancy: real
    exports populate one side or the other inconsistently, so consumers read
    whichever they were written against, and a node linked on only one side reads
    as missing to half of them.
    """
    cim = network.cim

    primary = members[0]
    node = cim.TopologicalNode(name=f'topo_{primary.name}' if primary.name
                               else f'topo_node_{number}')
    node.uuid()
    node.busNumber = number
    node.busName = node.name
    node.ConnectivityNodeContainer = primary.ConnectivityNodeContainer

    for connectivity_node in members:
        connectivity_node.TopologicalNode = node
        node.ConnectivityNodes.append(connectivity_node)

        for terminal in connectivity_node.Terminals:
            terminal.TopologicalNode = node
            node.Terminal.append(terminal)

    node.BaseVoltage = _base_voltage(members)

    network.add_to_graph(node)
    return node


def _base_voltage(members: list) -> cim.BaseVoltage | None:
    """The BaseVoltage of a bus, taken from its container or its equipment.

    A merged node can span more than one nominal voltage when transformers are not
    boundaries, so this is the voltage of the first thing that declares one rather
    than a claim about the whole bus. Callers that need per-voltage buses should
    build with ``xfmr_boundary=True``.
    """
    for connectivity_node in members:
        container = connectivity_node.ConnectivityNodeContainer
        base_voltage = getattr(container, 'BaseVoltage', None)
        if base_voltage is not None:
            return base_voltage

    for connectivity_node in members:
        for terminal in connectivity_node.Terminals:
            equipment = terminal.ConductingEquipment
            base_voltage = getattr(equipment, 'BaseVoltage', None)
            if base_voltage is not None:
                return base_voltage

    return None
