from __future__ import annotations

import importlib
import logging
import cimgraph.data_profile.cimhub_2023 as cim_profile
from cimgraph.models import NodeBreakerModel
from cimgraph.databases import get_cim_profile
from cimtopology.substation.bus_number_mapper import BusNumberMapper

_log = logging.getLogger(__name__)

def clean_topology(network:NodeBreakerModel) -> None:
    cim:cim_profile = network.cim
    
    for terminal in network.list_by_class(cim.Terminal):
        terminal.__traversed__ = False
        terminal.__is_boundary__ = False
        
    for voltage_level in network.list_by_class(cim.VoltageLevel):
        voltage_level.__bus_count__ = 0


def process_base_topology(network: NodeBreakerModel, bus_mapper):
    cim:cim_profile = network.cim

    # Initialize bus number mapper for persistent numbering
    # bus_mapper = BusNumberMapper(network)

    for busbar in network.list_by_class(cim.BusbarSection):
        container = busbar.EquipmentContainer
        terminal = busbar.Terminals[0]
        bus_number, bus_name = bus_mapper.get_bus_number_and_name(busbar)
        bus_marker = cim.BusNameMarker(name=bus_number, aliasName=bus_name)
        bus_marker.Terminal = terminal
        terminal.BusNameMarker = bus_marker

        # ugly logic for figuring out bus_marker priority
        # try:
        #     # hard code first pass based on PSM BaseCase
        #     bus_marker.priority = int(busbar.name.split('Bus ')[1])
        #     container.__bus_count__ += 1
        # except:
        container.__bus_count__ += 1
        bus_marker.priority = container.__bus_count__

        network.add_to_graph(bus_marker)

        process_busbar_topology(network, busbar, bus_mapper)
        



def process_busbar_topology(network:NodeBreakerModel, busbar:cim_profile.BusbarSection, bus_mapper: BusNumberMapper):
    cim:cim_profile = importlib.import_module(busbar.__class__.__module__)
    first_terminal = busbar.Terminals[0]

    node = first_terminal.ConnectivityNode
    topo_node = first_terminal.TopologicalNode
    container = node.ConnectivityNodeContainer

    process_bus_topology(network, first_terminal, bus_mapper, busbar)
                            
def process_bus_topology(network, first_terminal:cim.Terminal, bus_mapper: BusNumberMapper, busbar: cim_profile.BusbarSection=None):
    cim:cim_profile = importlib.import_module(first_terminal.__class__.__module__)

    node = first_terminal.ConnectivityNode
    topo_node = first_terminal.TopologicalNode
    container = node.ConnectivityNodeContainer

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
        setattr(topo_node, 'aliasName', bus_number)


        network.add_to_graph(topo_node)
    
    for terminal in node.Terminals:
        try:
            if not terminal.__traversed__:
                terminal.__traversed__ = True
                terminal.TopologicalNode = topo_node
                topo_node.Terminal.append(terminal)
                equipment = terminal.ConductingEquipment
                if isinstance(equipment,cim.Switch):

                    # if not equipment.open and not equipment.retained:
                    if not equipment.retained:
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
                            

def get_base_voltage_from_node(node:cim_profile.ConnectivityNode) -> cim_profile.BaseVoltage:
    voltages = []
    for terminal in node.Terminals:
        equipment = terminal.ConductingEquipment
        base_voltage = equipment.BaseVoltage
        if base_voltage is not None:
            voltages.append(base_voltage)
            
        
    