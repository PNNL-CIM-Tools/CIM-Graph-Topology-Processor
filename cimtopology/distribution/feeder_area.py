import logging
from uuid import UUID
from cimgraph.models import FeederModel, DistributedArea
from cimtopology.distribution.distributed_topology import (
    get_switch_classes, expand_to_boundaries, assign_to_area, mark_boundary, nest_area
)

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
    # cimhub_2026 replaced the FeederArea/DistributionArea/SwitchArea/SecondaryArea
    # classes with one ConnectivityArea discriminated by `areaType`, nested through
    # ContainedWithin/ContainedAreas rather than a class-specific association each.
    feeder_area = cim.ConnectivityArea(areaType = cim.ConnectivityAreaKind.feederArea)
    feeder_area.uuid(name = feeder.mRID)
    distribution_area = cim.ConnectivityArea(
        areaType = cim.ConnectivityAreaKind.distributionArea)
    distribution_area.uuid(name = geo_region.mRID)

    nest_area(feeder_area, distribution_area)

    feeder_model.add_to_graph(feeder_area)
    feeder_model.add_to_graph(distribution_area)

    # Create CIM-Graph distributed model
    feeder_area_model = DistributedArea(connection = feeder_model.connection,
                                container = feeder_area, distributed = True)
    feeder_area_model.add_to_graph(feeder)
    feeder_area_model.add_to_graph(feeder_area)

    # Initialize state for topology traversal
    boundaries = []
    parsed = []
    contained_equipment = []
    switch_classes = get_switch_classes(cim)

    # Add all switches to FeederArea
    for cim_class in switch_classes:
        for switch in feeder_model.graph.get(cim_class, {}).values():
            assign_to_area(switch, feeder_area)
            feeder_area_model.add_to_graph(switch)

    # Build topology tree from head terminal to first switch
    for head_terminal in feeder.NormalHeadTerminal:
        mark_boundary(head_terminal, feeder_area)
        expand_to_boundaries(head_terminal, feeder_area_model, feeder_area, cim,
                           boundaries, parsed, contained_equipment, switch_classes,
                           xfmr_boundary=False)

    # Build topology tree from slack bus to first switch
    for energy_source in feeder_model.graph.get(cim.EnergySource, {}).values():
        terminal = energy_source.Terminals[0]
        expand_to_boundaries(terminal, feeder_area_model, feeder_area, cim,
                           boundaries, parsed, contained_equipment, switch_classes,
                           xfmr_boundary=False)

    # Add list of boundary terminals
    feeder_area_model.boundaries = boundaries

    return feeder_area_model