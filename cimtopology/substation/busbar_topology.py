from __future__ import annotations

import importlib
import logging
from cimgraph.models import NodeBreakerModel
from cimtopology.substation.bus_number_mapper import BusNumberMapper

_log = logging.getLogger(__name__)


def _shunt_types(cim):
    """Shunt equipment types: single-terminal devices that inject/consume power."""
    return (cim.EnergyConsumer, cim.ShuntCompensator,
            cim.RotatingMachine, cim.StaticVarCompensator)


def process_topology(network: NodeBreakerModel, bus_mapper: BusNumberMapper) -> None:
    """Full node-breaker to bus-branch topology processing.

    Call this after switch states (open/closed) have been set on the network.
    Creates TopologicalNodes with bus numbers and BusNameMarkers.

    Handles isolated shunt equipment behind open breakers by assigning it to
    the upstream bus and marking it out of service.
    """
    cim = network.cim

    clean_topology(network)
    process_base_topology(network, bus_mapper)

    # Expand topology through closed switches at junctions not yet reached
    for switch_cls in (cim.Breaker, cim.Disconnector):
        for switch in network.list_by_class(switch_cls):
            if switch.open:
                continue
            for terminal in switch.Terminals:
                if terminal.TopologicalNode is None:
                    junction = _find_junction(terminal.ConnectivityNode)
                    if junction:
                        process_bus_topology(
                            first_terminal=terminal, network=network,
                            bus_mapper=bus_mapper, busbar=junction,
                        )

    # Assign isolated shunt equipment to upstream bus (through open switches)
    _assign_isolated_shunts(network)

    # Remaining unassigned terminals (transformers, lines, etc. at junctions)
    for terminal in network.list_by_class(cim.Terminal):
        if terminal.TopologicalNode is None:
            junction = _find_junction(terminal.ConnectivityNode)
            if junction:
                process_bus_topology(
                    first_terminal=terminal, network=network,
                    bus_mapper=bus_mapper, busbar=junction,
                )

    topo_count = len(network.list_by_class(cim.TopologicalNode))
    _log.info(f"Topology complete: {topo_count} TopologicalNodes")


def _find_junction(connectivity_node):
    """Find a Junction connected to a ConnectivityNode."""
    for term in connectivity_node.Terminals:
        if type(term.ConductingEquipment).__name__ == 'Junction':
            return term.ConductingEquipment
    return None


def _assign_isolated_shunts(network: NodeBreakerModel) -> None:
    """Find shunt equipment with no TopologicalNode and assign to upstream bus.

    Traces from the shunt's ConnectivityNode across open switches to find the
    nearest TopologicalNode on the busbar side. Assigns the shunt (and all
    intermediate terminals) to that node, and marks the equipment out of service.

    Physical model: Generator/Load -- [CN] -- OpenBreaker -- [CN] -- Busbar
    The shunt side of the open breaker has no TopologicalNode yet.
    We trace through the open switch to find the busbar's TopologicalNode.
    """
    cim = network.cim
    shunt_types = _shunt_types(cim)

    for terminal in network.list_by_class(cim.Terminal):
        if terminal.TopologicalNode is not None:
            continue
        equipment = terminal.ConductingEquipment
        if not isinstance(equipment, shunt_types):
            continue

        # Trace from this shunt's ConnectivityNode to find the upstream bus
        upstream = _trace_to_upstream_bus(terminal.ConnectivityNode, cim)
        if upstream is None:
            _log.warning(
                f"Isolated shunt '{equipment.name}' has no reachable upstream bus"
            )
            continue

        topo_node, bus_marker = upstream

        # Assign the shunt terminal to the upstream bus
        terminal.TopologicalNode = topo_node
        terminal.BusNameMarker = bus_marker
        if terminal not in topo_node.Terminal:
            topo_node.Terminal.append(terminal)
        terminal.__traversed__ = True

        # Also assign the switch terminal on the shunt side
        for cn_terminal in terminal.ConnectivityNode.Terminals:
            if cn_terminal.TopologicalNode is None:
                cn_terminal.TopologicalNode = topo_node
                cn_terminal.BusNameMarker = bus_marker
                if cn_terminal not in topo_node.Terminal:
                    topo_node.Terminal.append(cn_terminal)
                cn_terminal.__traversed__ = True

        equipment.inService = False
        _log.info(f"Shunt '{equipment.name}' assigned to bus "
                  f"{topo_node.aliasName}, marked out of service")


def _trace_to_upstream_bus(start_cn, cim) -> tuple | None:
    """BFS from a ConnectivityNode across open switches to find an assigned bus.

    Returns (TopologicalNode, BusNameMarker) if found, else None.
    Only crosses Switch equipment (open or closed, non-retained).
    """
    visited = {id(start_cn)}
    queue = [start_cn]

    while queue:
        cn = queue.pop(0)

        # Check if any terminal on this CN already has a TopologicalNode
        for term in cn.Terminals:
            if term.TopologicalNode is not None:
                return (term.TopologicalNode, term.BusNameMarker)

        # Try crossing switches connected to this CN
        for term in cn.Terminals:
            equip = term.ConductingEquipment
            if not isinstance(equip, cim.Switch):
                continue
            if equip.retained:
                continue
            # Cross to the other side of the switch
            for far_term in equip.Terminals:
                far_cn = far_term.ConnectivityNode
                if id(far_cn) not in visited:
                    visited.add(id(far_cn))
                    queue.append(far_cn)

    return None


def clean_topology(network: NodeBreakerModel) -> None:
    cim = network.cim

    for terminal in network.list_by_class(cim.Terminal):
        terminal.__traversed__ = False
        terminal.__is_boundary__ = False

    for voltage_level in network.list_by_class(cim.VoltageLevel):
        voltage_level.__bus_count__ = 0


def process_base_topology(network: NodeBreakerModel, bus_mapper):
    cim = network.cim

    retained_junction = []
    retained_switch = network.find_by_attribute(cim.Breaker, 'retained', True)
    for switch in retained_switch:
        for terminal in switch.Terminals:
            for next_terminal in terminal.ConnectivityNode.Terminals:
                if isinstance(next_terminal.ConductingEquipment, cim.Junction):
                    retained_junction.append(next_terminal.ConductingEquipment)

    for busbar in network.list_by_class(cim.BusbarSection) + retained_junction:
        container = busbar.EquipmentContainer
        terminal = busbar.Terminals[0]
        bus_number, bus_name = bus_mapper.get_bus_number_and_name(busbar)
        bus_marker = cim.BusNameMarker(name=bus_number, aliasName=bus_name)
        bus_marker.Terminal = terminal
        terminal.BusNameMarker = bus_marker
        container.__bus_count__ += 1
        bus_marker.priority = container.__bus_count__

        network.add_to_graph(bus_marker)

        process_busbar_topology(network, busbar, bus_mapper)


def process_busbar_topology(network: NodeBreakerModel, busbar, bus_mapper: BusNumberMapper):
    cim = importlib.import_module(busbar.__class__.__module__)
    first_terminal = busbar.Terminals[0]

    node = first_terminal.ConnectivityNode
    topo_node = first_terminal.TopologicalNode
    container = node.ConnectivityNodeContainer

    process_bus_topology(network, first_terminal, bus_mapper, busbar)


def process_bus_topology(network, first_terminal, bus_mapper: BusNumberMapper, busbar=None):
    cim = importlib.import_module(first_terminal.__class__.__module__)

    node = first_terminal.ConnectivityNode
    topo_node = first_terminal.TopologicalNode
    container = node.ConnectivityNodeContainer
    bus_marker = first_terminal.BusNameMarker
    if bus_marker is None:
        bus_number, bus_name = bus_mapper.get_bus_number_and_name(busbar)
        bus_marker = cim.BusNameMarker(name=bus_number, aliasName=bus_name)
        first_terminal.BusNameMarker = bus_marker
        bus_marker.TopologicalNode = topo_node
        network.add_to_graph(bus_marker)

    if topo_node is None:
        topo_node = cim.TopologicalNode(name='topo_' + node.name)
        topo_node.ConnectivityNodeContainer = container
        topo_node.BusNameMarker.append(bus_marker)
        topo_node.BaseVoltage = container.BaseVoltage
        first_terminal.TopologicalNode = topo_node
        first_terminal.BusNameMarker = bus_marker
        node.TopologicalNode = topo_node
        topo_node.Terminal.append(first_terminal)
        topo_node.ConnectivityNodes.append(first_terminal.ConnectivityNode)
        bus_marker.TopologicalNode = topo_node

        # Use the bus number already assigned to the BusNameMarker
        topo_node.aliasName = bus_marker.name

        network.add_to_graph(topo_node)

    for terminal in node.Terminals:
        if not terminal.__traversed__:
            terminal.__traversed__ = True
            terminal.TopologicalNode = topo_node
            terminal.BusNameMarker = bus_marker
            topo_node.Terminal.append(terminal)
            equipment = terminal.ConductingEquipment
            if isinstance(equipment, cim.Switch):
                if not equipment.retained:
                    if not equipment.open:
                        for next_terminal in equipment.Terminals:
                            if not next_terminal.__traversed__:
                                next_terminal.TopologicalNode = topo_node
                                next_terminal.BusNameMarker = bus_marker
                                next_terminal.ConnectivityNode.TopologicalNode = topo_node
                                topo_node.Terminal.append(next_terminal)
                                topo_node.ConnectivityNodes.append(next_terminal.ConnectivityNode)
                                process_bus_topology(network, next_terminal, bus_mapper=bus_mapper, busbar=busbar)


def get_base_voltage_from_node(node):
    voltages = []
    for terminal in node.Terminals:
        equipment = terminal.ConductingEquipment
        base_voltage = equipment.BaseVoltage
        if base_voltage is not None:
            voltages.append(base_voltage)
