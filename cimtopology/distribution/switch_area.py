import logging

from cimgraph.models import FeederModel, DistributedArea
from cimtopology.distribution.distributed_topology import DistributedTopology

_log = logging.getLogger(__name__)


def create_switch_areas(feeder_model: FeederModel, feeder_area_model: DistributedArea) -> list[DistributedArea]:
    """
    Creates switch areas from the provided feeder model and appends them to the feeder area model.

    This function initializes SwitchArea container objects for each switch found in the feeder model,
    builds the CIM-Graph distributed models, and constructs the topology trees from the terminals
    of each switch. It expands the topology to the boundaries for each terminal and updates the 
    boundaries in the switch area model.

    Args:
        feeder_model (FeederModel): The feeder model containing the CIM and graph information.
        feeder_area_model (DistributedArea): The distributed area model containing the feeder area.

    Returns:
        list[DistributedArea]: A list of the created switch area models added to the feeder area model.
    """
    cim = feeder_model.cim
    feeder_id = feeder_model.container.identifier
    feeder = feeder_model.graph[cim.Feeder][feeder_id]
    feeder_area = feeder_area_model.container

    switch_classes = [cim.Breaker, cim.Sectionaliser,
                cim.Recloser, cim.LoadBreakSwitch, cim.Switch]
    counter = -1
    for cim_class in switch_classes:
        # Loop through all switches in the model
        for switch in feeder_model.graph.get(cim_class, {}).values():
            # Loop through both terminals of the switch
            for terminal in switch.Terminals:
                # If terminal has an associated SwitchArea, then we already parsed it
                if terminal.BoundedSchedulingArea is None:
                    # Create a SwitchArea container following the naming convention of GridAPPS-D python
                    counter += 1
                    name = f'{feeder.mRID}.{counter}'
                    switch_area = cim.SwitchArea()
                    switch_area.uuid(name = name)
                    switch_area.name = name
                    switch_area.FeederArea = feeder_area
                    feeder_model.add_to_graph(switch_area)
                    
                    # Create CIM-Graph Distributed GraphModel class
                    switch_area_model = DistributedArea(connection = feeder_model.connection,
                                                container = switch_area, distributed = True)
                    
                    # Load topology for current switch area and parse to next switch(es)
                    Topology = DistributedTopology(switch_area_model)
                    Topology.expand_to_boundaries(terminal)
                    switch_area_model.boundaries = Topology.boundaries
                    feeder_area_model.distributed_areas.append(switch_area_model)
                    
                    # Add transformers to the switch area
                    for transformer in switch_area_model.graph.get(cim.PowerTransformer, {}).values():
                        transformer.SubSchedulingArea = switch_area_model.container
                        switch_area_model.add_to_graph(transformer)

    return feeder_area_model.distributed_areas
