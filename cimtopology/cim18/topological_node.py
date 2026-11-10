"""TopologicalNodes (buses) of a cim18v17 model, feeder or node-breaker substation.

A TopologicalNode is the set of ConnectivityNodes joined by bus ties: closed switches that are not
retained (IEC 61970-301; ``switching.is_bus_tie``). Lines and transformers have impedance, so their
ends are always different buses. An open or retained switch splits a bus. This is the rule of cim17
``substation/busbar_topology.py``, worked out as one LinkNet spanning forest over every
ConnectivityNode, so every node lands in exactly one bus and none is left floating.

Two cim17 defects are fixed by construction:

- the topology a model already carries is deleted first (cim17 kept it, so a rebuild changed nothing);
- every association is written from both sides: Terminal <-> TopologicalNode and
  ConnectivityNode <-> TopologicalNode (cim17 missed ``ConnectivityNode.TopologicalNode``, and the
  nodes drew as floating).

cim17 also folded a shunt stranded behind an open breaker into the busbar's bus and set it out of
service, a PSS/E export convention. That is not done here: such a shunt gets its own bus (and a
dead island), and ``inService`` is never changed.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from cimtopology.cim18.index import ModelIndex, index_model, label
from cimtopology.cim18.switching import is_bus_tie
from cimtopology.core.linknet import spanning_forest

if TYPE_CHECKING:
    from cimgraph.models import GraphModel


def clear_topology(model: GraphModel) -> None:
    """Delete every TopologicalIsland and TopologicalNode and every reference to them, both sides."""
    cim = model.cim
    for cim_class in (cim.TopologicalIsland, cim.TopologicalNode):
        for obj in list(model.graph.get(cim_class, {}).values()):
            model.delete(obj)
    # a file may carry only one side of an association, which delete() cannot see from the other
    for terminal in model.graph.get(cim.Terminal, {}).values():
        terminal.TopologicalNode = None
    for node in model.graph.get(cim.ConnectivityNode, {}).values():
        node.TopologicalNode = None


def bus_roots(index: ModelIndex, cim) -> list[int]:
    """LinkNet node -> the node that roots its bus (entry 0 unused)."""
    ties = [False] + [is_bus_tie(equipment, cim) for equipment in index.equipment[1:]]
    forest = spanning_forest(index.linknet, range(1, index.linknet.node_count + 1),
                             crosses=lambda equipment: ties[equipment])
    return forest.tree_of


def build_topological_nodes(model: GraphModel) -> list:
    """Replace the model's TopologicalNodes with one per bus, and return them."""
    cim = model.cim
    clear_topology(model)
    index = index_model(model)
    members: dict[int, list[int]] = {}
    for node, root in enumerate(bus_roots(index, cim)[1:], start=1):
        members.setdefault(root, []).append(node)

    buses = []
    for root, nodes in members.items():
        first = index.nodes[root]
        bus = cim.TopologicalNode(name=first.name or first.mRID)
        bus.uuid(mRID=f'tn_{first.mRID or first.identifier}')
        container = first.ConnectivityNodeContainer
        if container is not None:
            bus.ConnectivityNodeContainer = container
            container.TopologicalNode.append(bus)
        terminals = [index.terminals[terminal] for node in nodes for terminal in index.linknet.terminals(node)]
        bus.BaseVoltage = _base_voltage(bus, [index.nodes[node] for node in nodes], terminals, cim)
        for node in nodes:
            connectivity_node = index.nodes[node]
            connectivity_node.TopologicalNode = bus
            bus.ConnectivityNodes.append(connectivity_node)
        for terminal in terminals:
            terminal.TopologicalNode = bus
            bus.Terminal.append(terminal)
        model.add_to_graph(bus)
        buses.append(bus)
    return buses


def _base_voltage(bus, connectivity_nodes: list, terminals: list, cim):
    """The one BaseVoltage the bus's nodes, their containers and their equipment agree on.

    A transformer terminal's voltage is its end's BaseVoltage (the PowerTransformer's own is not to be
    used, per the profile). Different values on one bus raise; no value at all gives None.
    """
    found = []
    for node in connectivity_nodes:
        found.append(node.BaseVoltage)
        if isinstance(node.ConnectivityNodeContainer, cim.VoltageLevel):
            found.append(node.ConnectivityNodeContainer.BaseVoltage)
    for terminal in terminals:
        equipment = terminal.ConductingEquipment
        if isinstance(equipment, cim.PowerTransformer):
            found += [end.BaseVoltage for end in equipment.PowerTransformerEnd if end.Terminal is terminal]
        elif isinstance(equipment, cim.AutoTransformer):
            found += [end.BaseVoltage for end in equipment.AutoTransformerEnd if end.Terminal is terminal]
        else:
            found.append(equipment.BaseVoltage)
    found = [base for base in found if base is not None]
    if not found:
        return None
    volts = float(found[0].nominalVoltage)
    for base in found[1:]:
        if not math.isclose(float(base.nominalVoltage), volts, rel_tol=1e-6):
            raise ValueError(f"TopologicalNode {label(bus)}: its equipment is at both {volts:g} V "
                             f"({label(found[0])}) and {float(base.nominalVoltage):g} V ({label(base)})")
    return found[0]
