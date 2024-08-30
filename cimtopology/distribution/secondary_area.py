import logging

from cimgraph.models import FeederModel, DistributedArea
from cimtopology.distribution.distributed_topology import DistributedTopology

_log = logging.getLogger(__name__)


def create_secondary_areas(feeder_model: FeederModel, switch_area_model: DistributedArea) -> list[DistributedArea]:
    cim = feeder_model.cim
    counter = -1
    for boundary_terminal in switch_area_model.boundaries:
        boundary_equipment = boundary_terminal.ConductingEquipment
        if boundary_equipment.__class__ == cim.PowerTransformer:
            for terminal in boundary_equipment.Terminals:
                if terminal.BoundedResourceContainer is None:
                    counter += 1
                    sec_area = cim.SecondaryArea()
                    sec_area.uuid(name = f'{switch_area_model.container.name}.{counter}')

                    SecDistArea = DistributedArea(connection = feeder_model.connection,
                                            container = sec_area,
                                            distributed = True)

                    Topology = DistributedTopology(SecDistArea)

                    Topology.expand_to_boundaries(terminal)
                    switch_area_model.boundaries = Topology.boundaries
                    switch_area_model.distributed_areas.append(SecDistArea)
    
    return switch_area_model.distributed_areas