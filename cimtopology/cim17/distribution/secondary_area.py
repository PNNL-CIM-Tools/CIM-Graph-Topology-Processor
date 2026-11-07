import logging

from cimgraph.models import FeederModel, DistributedArea
from cimtopology.cim17.distribution.distributed_topology import (
    get_switch_classes, expand_to_boundaries
)

_log = logging.getLogger(__name__)


def create_secondary_areas(feeder_model: FeederModel, switch_area_model: DistributedArea) -> list[DistributedArea]:
    """
    Creates secondary areas from the provided feeder model and appends them to the switch area model.

    This function identifies boundary terminals in the switch area model to find power transformers
    that create secondary areas. It initializes SecondaryArea container objects for each identified
    transformer, builds the CIM-Graph distributed models, and constructs the topology trees from the
    transformer terminals. It expands the topology to the boundaries for each terminal and updates the 
    boundaries in the secondary area model.

    Args:
        feeder_model (FeederModel): The feeder model containing the CIM and graph information.
        switch_area_model (DistributedArea): The distributed area model containing the switch area.

    Returns:
        list[DistributedArea]: A list of the created secondary area models added to the switch area model.
    """
    cim = feeder_model.cim
    counter = -1
    switch_area = switch_area_model.container
    switch_classes = get_switch_classes(cim)
    # We can use the boundaries identified by switch area topology rather
    # parsing through all the transformers again to eliminate regulators
    for boundary_terminal in switch_area_model.boundaries:
        boundary_equipment = boundary_terminal.ConductingEquipment
        # If boundary is a transformer with terminal that does not bound
        # another SubSchedulingArea, then we can assume it is a SecondaryArea
        if boundary_equipment.__class__ == cim.PowerTransformer:
            for terminal in boundary_equipment.Terminals:
                if terminal.BoundedSchedulingArea is None:
                    # Create new SecondaryArea using GridAPPS-D naming
                    counter += 1
                    name = f'{switch_area_model.container.name}.{counter}'
                    sec_area = cim.SecondaryArea()
                    sec_area.uuid(name = name)
                    sec_area.SwitchArea = switch_area
                    feeder_model.add_to_graph(sec_area)
                    # Create CIM-Graph Distributed Model
                    SecDistArea = DistributedArea(connection = feeder_model.connection,
                                            container = sec_area, distributed = True)

                    # Initialize state for topology traversal
                    boundaries = []
                    parsed = []
                    contained_equipment = []

                    # Load topology and expand from transformer terminal
                    expand_to_boundaries(terminal, SecDistArea, sec_area, cim,
                                       boundaries, parsed, contained_equipment, switch_classes)
                    switch_area_model.boundaries = boundaries
                    switch_area_model.distributed_areas.append(SecDistArea)

    return switch_area_model.distributed_areas