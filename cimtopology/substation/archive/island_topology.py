from __future__ import annotations

import importlib
import logging
import cimgraph.data_profile.cimhub_2023 as cim_profile
from cimgraph.models import NodeBreakerModel
from cimgraph.databases import get_cim_profile
from cimtopology.substation.archive.bus_number_mapper import BusNumberMapper


def process_island_topology(network, busbar:cim_profile.BusbarSection, bus_mapper:BusNumberMapper):
    cim:cim_profile = importlib.import_module(first_terminal.__class__.__module__)
    first_terminal = busbar.Terminals[0]
    node = first_terminal.ConnectivityNode
    topo_node = first_terminal.TopologicalNode
    container = node.ConnectivityNodeContainer
    island = cim.TopologicalIsland(name='island_1')

    if topo_node is None:
        topo_node = cim.TopologicalNode(name='topo_'+node.name)
        topo_node.ConnectivityNodeContainer = container
        topo_node.BusNameMarker = first_terminal.BusNameMarker
        topo_node.BaseVoltage = container.BaseVoltage
        topo_node.ControlArea = node.ControlArea
        first_terminal.TopologicalNode = topo_node
        node.TopologicalNode = topo_node
        topo_node.Terminal.append(first_terminal)
        topo_node.ConnectivityNodes.append(first_terminal.ConnectivityNode)


        bus_number, bus_name = bus_mapper.get_bus_number_and_name(busbar)
        setattr(topo_node, 'busNumber', bus_number)
        setattr(topo_node, 'aliasName', bus_name)


        network.add_to_graph(topo_node)
    
    for terminal in node.Terminals:
        try:
            if not terminal.__traversed__:
                terminal.__traversed__ = True
                terminal.TopologicalNode = topo_node
                topo_node.Terminal.append(terminal)
                equipment = terminal.ConductingEquipment
                if isinstance(equipment,cim.Switch):
                    if not equipment.open and not equipment.retained:
                        for next_terminal in equipment.Terminals:
                            if not next_terminal.__traversed__:
                                next_terminal.TopologicalNode = topo_node
                                next_terminal.ConnectivityNode.TopologicalNode = topo_node
                                topo_node.Terminal.append(next_terminal)
                                topo_node.ConnectivityNodes.append(next_terminal.ConnectivityNode)
                                # Recursive call without busbar (bus number only assigned to initial node)
                                process_bus_topology(network, next_terminal, bus_mapper=bus_mapper, busbar=busbar)
        except:
            _log.warning(f'{terminal.name} of {terminal.ConductingEquipment.name} not traversed')
                            