import logging


from cimgraph.models import FeederModel, DistributedArea
from cimtopology.distribution.feeder_area import create_feeder_area
from cimtopology.distribution.switch_area import create_switch_areas
from cimtopology.distribution.secondary_area import create_secondary_areas
import cimgraph.utils as utils

_log = logging.getLogger(__name__)


# If GridAPPS-D Topology Processor output is not provided, build new topology:
def create_distributed_feeder(feeder_model: FeederModel, filename:str = None):
    """
    Creates the distributed feeder topology and writes it to an XML file.

    This function builds the topology for a given feeder model by retrieving all
    necessary edges, creating feeder areas, switch areas, and secondary areas. 
    The completed topology is then written to an XML file.

    Args:
        feeder_model (FeederModel): The feeder model containing the CIM and graph information.
        filename (str): Optional. The name of the file to which the topology will be written.
    """
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

    if filename is not None:
        utils.write_xml(feeder_model, filename)
    



        
def identify_addressable(network: DistributedArea, 
                         equipment_list: list[str] = []) -> list[str]:
    cim = network.cim
    addressable_classes = [cim.Switch, cim.Breaker, cim.Disconnector,
        cim.Recloser, cim.LoadBreakSwitch, cim.Sectionaliser,
        cim.PowerElectronicsConnection, cim.PowerElectronicsUnit,
        cim.PhotovoltaticUnit, cim.BatteryUnit, cim.PowerElectronicsWindUnit,
        cim.RatioTapChanger, 
        cim.ShuntCompensator, cim.LinearShuntCompensator,
        cim.AsynchronousMachine, cim.SynchronousMachine]
    
    for class_type in addressable_classes:
        for equipment in network.graph.get(class_type, {}).values():
            equipment_list.append(equipment.uri())
    return equipment_list

def identify_unaddressable(network: DistributedArea, 
                         equipment_list: list[str] = []) -> list[str]:
    cim = network.cim
    unaddressable_classes = [cim.ACLineSegment, cim.Fuse,
        cim.PowerTransformer, cim.TransformerTank,
        cim.EnergySource, cim.EnergyConsumer]
    
    for class_type in unaddressable_classes:
        for equipment in network.graph.get(class_type, {}).values():
            equipment_list.append(equipment.uri())
    return equipment_list

