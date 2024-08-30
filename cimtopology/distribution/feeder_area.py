import logging

from cimgraph.models import FeederModel, DistributedArea
from cimtopology.distribution.distributed_topology import DistributedTopology

_log = logging.getLogger(__name__)


def create_feeder_area(feeder_model: FeederModel) -> DistributedArea:

    cim = feeder_model.cim
    feeder = feeder_model.container
    feeder_area = cim.FeederArea()
    feeder_area.uuid(name = f'{feeder.mRID}')


    feeder_area_model = DistributedArea(connection = feeder_model.connection,
                                container = feeder_area,
                                distributed = True)

    Topology = DistributedTopology(feeder_area_model)

    # Add all switches to FeederArea
    for cim_class in Topology.switch_classes:
        for switch in feeder_model.graph.get(cim_class, {}).values():
            switch.ResourceContainer = feeder_area
            feeder_area_model.add_to_graph(switch)

    # Build topology tree from head terminal to first switch
    for head_terminal in feeder.NormalHeadTerminal:
        head_terminal.ResourceContainer = feeder_area
        Topology.expand_to_boundaries(head_terminal,xfmr_boundary=False)

    for energy_source in feeder_model.graph.get(cim.EnergySource, {}).values():
        terminal = energy_source.Terminals[0]
        Topology.expand_to_boundaries(terminal, xfmr_boundary=False)

    feeder_area_model.boundaries = Topology.boundaries

    return feeder_area_model