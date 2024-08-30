import logging

from cimgraph.models import FeederModel, DistributedArea
from cimtopology.distribution.distributed_topology import DistributedTopology

_log = logging.getLogger(__name__)


def create_switch_areas(feeder_model: FeederModel, feeder_area_model: DistributedArea) -> list[DistributedArea]:
    cim = feeder_model.cim
    feeder = feeder_model.container

    switch_classes = [cim.Breaker, cim.Sectionaliser,
                cim.Recloser, cim.LoadBreakSwitch, cim.Switch]
    counter = -1
    for cim_class in switch_classes:
        for switch in feeder_model.graph.get(cim_class, {}).values():
            for terminal in switch.Terminals:
                if terminal.BoundedResourceContainer is None:
                    counter += 1
                    switch_area = cim.SwitchArea()
                    switch_area.uuid(name = f'{feeder.mRID}.{counter}')


                    switch_area_model = DistributedArea(connection = feeder_model.connection,
                                                container = switch_area,
                                                distributed = True)

                    Topology = DistributedTopology(switch_area_model)

                    Topology.expand_to_boundaries(terminal)
                    switch_area_model.boundaries = Topology.boundaries
                    feeder_area_model.distributed_areas.append(switch_area_model)

                    for equipment in Topology.contained_equipment:
                        print(equipment.__class__.__name__, equipment.name)

    return feeder_area_model.distributed_areas
