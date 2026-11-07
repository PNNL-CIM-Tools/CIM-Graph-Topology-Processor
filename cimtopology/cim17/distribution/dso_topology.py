from __future__ import annotations
import logging

from cimgraph.models import FeederModel
import cimprofiles.cim18.cim18gmdm.canonical as cim

_log = logging.getLogger(__name__)

def divide_feeders(network:FeederModel):
    cim:cim = network.cim
    for cim_class in network.graph:
        if issubclass(cim_class, cim.Switch):
            for switch in network.list_by_class(cim_class):
                if 'hvmv' in switch.name.lower(): #TODO: temporary subtransmission logic for 9500
                    switch.normalOpen = True

    for cim_class in network.graph:
        if issubclass(cim_class, cim.Equipment):
            for equipment in network.list_by_class(cim_class):
                equipment.EquipmentContainer = None
                
    for node in network.list_by_class(cim.ConnectivityNode):
        node.ConnectivityNodeContainer = None
        
    for terminal in network.list_by_class(cim.Terminal):
        terminal.__traversed__ = False
        terminal.__is_boundary__ = False
            
            
def assign_equipment_container(terminal:cim.Terminal, container:cim.EquipmentContainer):
    node = terminal.ConnectivityNode
    for terminal in node.Terminals:
        if not terminal.__traversed__:
            terminal.__traversed__ = True
            equipment = terminal.ConductingEquipment
            # Assign new equipment container
            if equipment.EquipmentContainer is None:
                equipment.EquipmentContainer = container
            else:
                if isinstance(equipment, cim.Switch):
                    if equipment.EquipmentContainer.uri() != container.uri():
                        equipment.AdditionalEquipmentContainer = container
            # Assign new node container
            if terminal.ConnectivityNode.ConnectivityNodeContainer is None:
                terminal.ConnectivityNode.ConnectivityNodeContainer = container
            # Check if boundary reached
            if isinstance(equipment, cim.Switch):
                if equipment.normalOpen:
                    for next_terminal in equipment.Terminals:
                        next_terminal.__is_boundary__ = True
                    continue
            
            for next_terminal in equipment.Terminals:
                if not next_terminal.__traversed__:
                    if not next_terminal.__is_boundary__:
                        assign_equipment_container(next_terminal, container)
            
    
    
        
    
    
    
    
    
            
            
    