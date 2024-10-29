import logging
from uuid import UUID
from cimgraph.models import FeederModel, DistributedArea
from cimtopology.distribution.distributed_topology import DistributedTopology

_log = logging.getLogger(__name__)


def create_feeder_area(feeder_model: FeederModel) -> DistributedArea:
    """
    Creates the top-level feeder area from the provided feeder model and returns a distributed area.

    This function initializes a FeederArea container object, builds the CIM-Graph
    distributed model, and constructs the topology tree from head terminals to the first switch.
    It also handles the expansion of the topology from the slack bus to the first switch.

    Args:
        feeder_model (FeederModel): The centralized CIM-Graph model containing the full feeder.

    Returns:
        DistributedArea: The created distributed area model containing the topology and boundary information.
    """
    cim = feeder_model.cim
    feeder_id = feeder_model.container.identifier
    feeder = feeder_model.graph[cim.Feeder][feeder_id]
    substation = feeder.NormalEnergizingSubstation
    geo_region = substation.Region
    # Create FeederArea container object
    feeder_area = cim.FeederArea()
    feeder_area.uuid(name = feeder.mRID)
    distribution_area = cim.DistributionArea()
    distribution_area.uuid(name = geo_region.mRID)

    feeder_area.Feeder = feeder
    feeder_area.Substation = feeder.NormalEnergizingSubstation
    feeder_area.DistributionArea = distribution_area

    feeder.FeederArea = feeder_area
    feeder.DistributionArea = distribution_area
    
    substation.SchedulingArea = distribution_area

    feeder_model.add_to_graph(feeder_area)
    feeder_model.add_to_graph(distribution_area)

    # Create CIM-Graph distributed model
    feeder_area_model = DistributedArea(connection = feeder_model.connection,
                                container = feeder_area, distributed = True)
    feeder_area_model.add_to_graph(feeder)
    feeder_area_model.add_to_graph(feeder_area)
    
    # Create topology class to trace the local area
    Topology = DistributedTopology(feeder_area_model)

    # Add all switches to FeederArea
    for cim_class in Topology.switch_classes:
        for switch in feeder_model.graph.get(cim_class, {}).values():
            switch.SubSchedulingArea = feeder_area
            feeder_area_model.add_to_graph(switch)

    # Build topology tree from head terminal to first switch
    for head_terminal in feeder.NormalHeadTerminal:
        head_terminal.SubSchedulingArea = feeder_area
        Topology.expand_to_boundaries(head_terminal,xfmr_boundary=False)

    # Build topology tree from slack bus to first switch
    for energy_source in feeder_model.graph.get(cim.EnergySource, {}).values():
        terminal = energy_source.Terminals[0]
        Topology.expand_to_boundaries(terminal, xfmr_boundary=False)

    # Add list of boundary terminals
    feeder_area_model.boundaries = Topology.boundaries
    
    return feeder_area_model