"""Group TopologicalNodes into TopologicalIslands for a distribution feeder."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cimgraph.models import GraphModel

from cimtopology.core import node_of
from cimtopology.distribution.bus_topology import (
    bridging_equipment,
    equipment_terminals,
)

if TYPE_CHECKING:
    # Annotations only. The live profile comes from `network.cim` at runtime, so this
    # module works against whichever profile the caller's model was built with.
    import cimgraph.data_profile.cimhub_2026 as cim

_log = logging.getLogger(__name__)


def build_feeder_islands(network: GraphModel) -> list[cim.TopologicalIsland]:
    """Group the network's TopologicalNodes into energized TopologicalIslands.

    An island is a maximal set of TopologicalNodes that are galvanically connected
    through equipment currently able to conduct. Nodes separated by an open switch land
    in different islands, which is what makes this useful: it answers "what is still
    connected to what" after a switching operation or a fault.

    A transformer is a conducting branch, so its HV and LV sides are always in the same
    island. There is deliberately no option to change that: splitting at transformers is
    a question about *buses*, answered one layer down by
    ``build_bus_topology(xfmr_boundary=True)``. By the time islands are grouped, the
    windings are already separate TopologicalNodes and the island still spans them.

    Note this reports connectivity, not energization. An island with no EnergySource or
    SynchronousMachine in it is fully connected and completely de-energized -- a
    perfectly normal result after a fault. ``AngleRefTopologicalNode`` is how to tell:
    an island with no reference has nothing energizing it.

    The algorithm is a breadth-first flood fill over TopologicalNodes, in three steps:

    1. Delete any existing islands, so the result reflects current switch states.
    2. Walk the equipment once to build an adjacency map: node -> neighbouring nodes.
    3. Flood-fill that map, one island per sweep, until every node is assigned.

    Requires TopologicalNodes to exist already -- run ``build_bus_topology`` first, or
    use ``cimtopology.build_topology``, which does both. Repeated calls are safe.

    Returns the islands, largest first.
    """
    cim = network.cim

    _delete_existing_islands(network)

    nodes = network.list_by_class(cim.TopologicalNode)
    if not nodes:
        _log.warning('No TopologicalNodes in the model; nothing to group into islands')
        return []

    adjacency = _build_adjacency(network)
    groups = _flood_fill(nodes, adjacency)
    groups.sort(key=len, reverse=True)

    islands = [_create_island(network, members, number)
               for number, members in enumerate(groups, start=1)]

    sizes = ', '.join(str(len(members)) for members in groups)
    _log.info(f'Built {len(islands)} TopologicalIsland(s) from {len(nodes)} '
              f'TopologicalNodes (sizes: {sizes})')

    return islands


def _delete_existing_islands(network: GraphModel) -> None:
    """Drop existing islands so a rebuild reflects current switch states.

    Both back-references have to be nulled, not just the island objects removed: a
    node still pointing at a deleted island would report stale membership.
    """
    cim = network.cim

    for node in network.list_by_class(cim.TopologicalNode):
        node.TopologicalIsland = None
        node.AngleRefTopologicalIsland = None

    stale = network.list_by_class(cim.TopologicalIsland)
    for island in stale:
        network.graph[type(island)].pop(island.identifier, None)

    if stale:
        _log.debug(f'Cleared {len(stale)} pre-existing TopologicalIsland(s)')


def _build_adjacency(network: GraphModel) -> dict:
    """Map each TopologicalNode identifier to the nodes power can reach from it.

    One pass over the ConnectivityNodes, which is how the equipment is reached: the
    graph keys objects on their exact class, so a lookup for `Switch` returns nothing
    in a model whose switches are all Breakers and Reclosers.

    For each piece of equipment, the nodes its terminals sit on are mutually adjacent.
    Equipment is skipped when it cannot carry power (open switch, out of service), and
    that is the only thing that separates one island from the next.
    """
    cim = network.cim

    adjacency = {node.identifier: set()
                 for node in network.list_by_class(cim.TopologicalNode)}

    for equipment in _conducting_branches(network):
        # The nodes this equipment spans. Anything with fewer than two is a dead end
        # (a load, or a branch whose far side is outside this model) and adds no edge.
        spanned = {node.identifier
                   for node in (node_of(terminal)
                                for terminal in equipment_terminals(equipment))
                   if node is not None and node.identifier in adjacency}

        for identifier in spanned:
            adjacency[identifier].update(spanned - {identifier})

    return adjacency


def _conducting_branches(network: GraphModel) -> list:
    """Equipment that spans two or more nodes and can carry power between them.

    Branches are identified by counting terminals, not by matching a list of classes.
    Anything with two or more terminals joins the nodes they sit on -- that is what a
    branch *is* -- while a class list would have to name all 52 concrete
    ConductingEquipment subclasses to be complete, and silently drops an island edge
    for every one it misses. Single-terminal equipment (loads, sources, shunts) is
    excluded for free, since it spans nothing.

    `bridging_equipment` is what crosses a tank transformer, whose winding terminals
    carry `ConductingEquipment is None`; without it each of a real feeder's tank
    transformers would split the feeder.
    """
    cim = network.cim

    branches = {}
    for connectivity_node in network.list_by_class(cim.ConnectivityNode):
        for terminal in connectivity_node.Terminals or []:
            equipment = bridging_equipment(terminal)

            if equipment is None or equipment.identifier in branches:
                continue

            # Fewer than two terminals means it spans nothing -- a load, a source, or a
            # branch whose far side lies outside this model.
            if len(equipment_terminals(equipment)) < 2:
                continue

            if equipment.inService is False:
                continue

            # An open switching device breaks the path. `isinstance` on the Switch base
            # covers every one -- breaker, recloser, fuse, disconnector, earthing
            # switch, jumper, cut -- because islanding asks whether power can flow, not
            # whether an ADMS could operate it. (That is the separate, opt-in
            # `get_switch_classes` rule used for area boundaries.) A transformer needs
            # no such test: it conducts through its windings, not by being closed.
            if isinstance(equipment, cim.Switch) and equipment.open:
                continue

            branches[equipment.identifier] = equipment

    return list(branches.values())



def _flood_fill(nodes: list, adjacency: dict) -> list[list]:
    """Partition nodes into connected groups, one breadth-first sweep per group.

    Each sweep takes a seed and drains everything reachable from it out of
    `unassigned`, so a node can only ever join one group and the outer loop shrinks
    on every pass -- that is what guarantees termination. Iteration order is the
    graph's insertion order, so island numbering is stable across runs.
    """
    unassigned = {node.identifier: node for node in nodes}
    groups = []

    while unassigned:
        seed = unassigned.pop(next(iter(unassigned)))
        members = [seed]
        queue = [seed]

        while queue:
            node = queue.pop(0)
            for neighbour_id in adjacency.get(node.identifier, ()):
                neighbour = unassigned.pop(neighbour_id, None)
                if neighbour is not None:
                    members.append(neighbour)
                    queue.append(neighbour)

        groups.append(members)

    return groups


def _create_island(network: GraphModel, members: list,
                   number: int) -> cim.TopologicalIsland:
    """Build a TopologicalIsland over members and pick its angle reference.

    The angle reference is the node holding the island's voltage angle. Preference
    order follows what actually holds it: the energizing source first, then any
    rotating machine, since an island cut off from the source may still have local
    generation. An island with neither is left with no reference and logged, rather
    than given an arbitrary node.
    """
    cim = network.cim

    island = cim.TopologicalIsland(name=f'island_{number}')
    island.uuid()

    for node in members:
        node.TopologicalIsland = island
        island.TopologicalNodes.append(node)

    reference = _angle_reference(members, cim)
    if reference is not None:
        island.AngleRefTopologicalNode = reference
        reference.AngleRefTopologicalIsland = island
    else:
        _log.warning(f"Island '{island.name}' has no source or machine to serve as "
                     f'an angle reference ({len(members)} nodes)')

    network.add_to_graph(island)
    return island


def _angle_reference(members: list, cim) -> cim.TopologicalNode | None:
    """The node holding the island's voltage angle, or None if nothing energizes it.

    Only grid-forming equipment qualifies -- something that imposes a voltage angle
    rather than following one:

    * `EnergySource` is the feeder head, the substation supply. First choice.
    * `SynchronousMachine` is a local generator, which can hold up an island that has
      been cut off from the feeder head.
    * `PowerElectronicsConnection` only when `isGridForming` is explicitly True. The
      attribute is optional and left unset by every exporter seen so far (neither the
      ieee13 fixture nor the utility exports write it), and an unset value means "not
      stated", not
      "yes" -- so a plain grid-following PV inverter or battery is correctly ignored.

    `AsynchronousMachine` is deliberately excluded even though it is a `RotatingMachine`
    alongside SynchronousMachine: an induction machine follows the grid's angle and
    cannot establish one, so an island containing only induction machines is dead. An
    earlier version tested `RotatingMachine` and wrongly admitted them.

    Returns None when an island has no grid-forming equipment at all. That is a real and
    common answer -- a de-energized island after a fault -- not an error, so the caller
    is told rather than handed an arbitrary node.
    """
    fallback = None

    for node in members:
        # A TopologicalNode's terminals are reached through its ConnectivityNodes.
        # `node.Terminal` is the other side of the same association and is empty on
        # every model here (0 of 70 on ieee13), so walking the CNs is the path that
        # actually finds equipment.
        for connectivity_node in node.ConnectivityNodes:
            for terminal in connectivity_node.Terminals:
                equipment = terminal.ConductingEquipment

                if isinstance(equipment, cim.EnergySource):
                    return node

                # Local generation that can hold up an island on its own. A
                # PowerElectronicsConnection counts only when `isGridForming` is
                # explicitly True: it is optional, unset in every model here, and unset
                # means "not stated" rather than "yes".
                if fallback is None and (
                        isinstance(equipment, cim.SynchronousMachine)
                        or (isinstance(equipment, cim.PowerElectronicsConnection)
                            and equipment.isGridForming is True)):
                    fallback = node

    # No EnergySource anywhere in the island, so fall back to local generation.
    return fallback

