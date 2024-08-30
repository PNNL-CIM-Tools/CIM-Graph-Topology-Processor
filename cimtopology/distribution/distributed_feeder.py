import logging


from cimgraph.models import FeederModel
from cimtopology.distribution.feeder_area import create_feeder_area
from cimtopology.distribution.switch_area import create_switch_areas
from cimtopology.distribution.secondary_area import create_secondary_areas
import cimgraph.utils as utils

_log = logging.getLogger(__name__)


# If GridAPPS-D Topology Processor output is not provided, build new topology:
def create_distributed_feeder(feeder_model: FeederModel, filename):
    
    cim = feeder_model.cim
    feeder_model.get_all_edges(cim.PowerTransformer)
    feeder_model.get_all_edges(cim.TransformerTank)
    feeder_model.get_all_edges(cim.Asset)
    feeder_model.get_all_edges(cim.TransformerTankInfo)
    feeder_model.get_all_edges(cim.TransformerEndInfo)

    feeder_area_model = create_feeder_area(feeder_model)
    switch_area_models = create_switch_areas(feeder_model, feeder_area_model)
    for sw_area_model in switch_area_models:
        create_secondary_areas(feeder_model, sw_area_model)

    utils.write_xml(feeder_model, filename)
    

