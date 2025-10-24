from __future__ import annotations
import logging

from cimgraph.models import FeederModel
import cimgraph.data_profile.cim18gmdm.canonical as cim

_log = logging.getLogger(__name__)

def divide_feeders(network:FeederModel):
    cim:cim = network.cim
    counter = 1
    feeder = network.container or network.first(cim.Feeder)
    for terminal in network.list_by_class(cim.Terminal):
        if terminal.NormalHeadFeeder is not None:
            new_feeder = cim.Feeder(name=f'{feeder.name}_fdr_{counter}')
            trace_normal_feeder_topology(network, new_feeder, terminal)
            
            
            
def trace_normal_feeder_topology(network:FeederModel, new_feeder:cim.Feeder, head_termal:cim.Terminal):
    
    
    
    
def topo_tracer(starting_terminal:cim.Terminal):
    
    parsed=[starting_terminal]
    node = starting_terminal.ConnectivityNode
    
    for terminal in node.Terminals:
        equipment = terminal.ConductingEquipment
        
        if isinstance(equipment, cim.Switch):
            
            
    
    
        
    
    
    
    
    
            
            
    