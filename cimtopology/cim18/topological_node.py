"""TopologicalNodes (buses) of a cim18v17 model, feeder or node-breaker substation.

A TopologicalNode is the set of ConnectivityNodes joined by bus ties: closed switches that are not
retained (IEC 61970-301; ``switching.is_bus_tie``). Lines and transformers have impedance, so their
ends are always different buses. An open or retained switch splits a bus. This is the rule of cim17
``substation/busbar_topology.py``, worked out as one LinkNet spanning forest over every
ConnectivityNode, so every node lands in exactly one bus and none is left floating.

Two cim17 defects are fixed by construction:

- the topology a model already carries is deleted first (cim17 kept it, so a rebuild changed nothing),
  and that includes the ``SvVoltage``/``SvInjection`` state variables hanging from each bus -- a
  solved voltage belongs to the bus it was solved for and cannot outlive it (:func:`clear_topology`);
- every association is written from both sides: Terminal <-> TopologicalNode and
  ConnectivityNode <-> TopologicalNode (cim17 missed ``ConnectivityNode.TopologicalNode``, and the
  nodes drew as floating).

cim17 also folded a shunt stranded behind an open breaker into the busbar's bus and set it out of
service, a PSS/E export convention. That is not done here: such a shunt gets its own bus (and a
dead island), and ``inService`` is never changed.

**This module owns a bus's state variables, both their creation and their removal.** Every bus gets
one empty ``SvVoltage`` and one ``SvInjection`` (:func:`build_state_variables`), and a rebuild
deletes them first (:func:`clear_topology`). Neither class has any reference field but
``TopologicalNode``, so neither can exist before the buses do and neither may outlive them -- which
makes this the only place the association can be written. The values are left unset: a solver, a
case importer or a telemetry fold fills them in by reaching the object through its bus.
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
    """Delete every TopologicalIsland and TopologicalNode and every reference to them, both sides.

    ``SvVoltage`` and ``SvInjection`` go too, and before the nodes they hang from. Both are state
    variables *of a bus*: neither is an IdentifiedObject, neither has an mRID, and the only thing
    either references is its TopologicalNode. So a bus's solved voltage cannot outlive the bus.

    ``model.delete()`` alone does not achieve this. It syncs inverse references, and
    ``TopologicalNode.SvVoltage`` is a declared field, so deleting a node *nulls* its SvVoltage's
    reference -- leaving the object in the graph, holding a voltage, belonging to no bus. Measured on
    a 2,678-node node-breaker model: rebuilding dropped 2,678 nodes to 280 buses while all 2,678
    SvVoltages survived, 0 of them referencing a live bus, and ``get_node_voltage`` then returned
    None for all 280 real buses. A PSS/E export reads its bus voltages through that getter, so the
    solved case was silently lost -- no exception, just no voltages.

    Deleting the dependents first is what makes it a clean sweep rather than a null-out.
    """
    cim = model.cim
    for cim_class in (cim.SvVoltage, cim.SvInjection, cim.TopologicalIsland, cim.TopologicalNode):
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


def build_state_variables(model: GraphModel, buses: list) -> None:
    """Give each bus in *buses* one empty ``SvVoltage`` and one ``SvInjection``, both sides written.

    A bus's state variables are **part of the bus**, which is why they are built here rather than by
    whoever later fills them in. Only this module knows which ConnectivityNodes merged into which
    bus, and an ``Sv*`` object has nowhere else to attach: ``SvVoltage``'s only reference field is
    ``TopologicalNode`` (its fields are ``identifier``, ``angle``, ``phase``, ``v``,
    ``TopologicalNode``), and ``SvInjection``'s are the same shape. There is no ``ConnectivityNode``
    field on either, so neither can be written before the buses exist -- an importer reading a
    node-breaker source has no bus to point at, and the grouping is snapshot-scoped anyway (a
    different switch state gives different buses).

    The objects are created **empty**: ``v``, ``angle``, ``pInjection`` and ``qInjection`` are all
    left ``None``. This slice owns the association, not the solved value. A solver, a case importer
    or the 1 Hz telemetry fold fills them in afterwards by looking the object up through its bus,
    which is the one join that is always available.

    Each is paired with exactly one bus, because ``get_node_voltage`` raises on a bus holding two
    balanced ``SvVoltage``s. Note the reverse associations are **lists**, so these append.

    :func:`clear_topology` deletes them again on the next rebuild, before the nodes they hang from.
    """
    cim = model.cim
    for bus in buses:
        voltage = cim.SvVoltage(TopologicalNode=bus)
        voltage.uuid()
        bus.SvVoltage.append(voltage)
        model.add_to_graph(voltage)

        injection = cim.SvInjection(TopologicalNode=bus)
        injection.uuid()
        bus.SvInjection.append(injection)
        model.add_to_graph(injection)


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
    build_state_variables(model, buses)
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
