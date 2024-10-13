from cimgraph.databases import ConnectionInterface
from cimgraph.models import FeederModel, DistributedArea
import cimgraph.data_profile.cimhub_2023 as cim
import cimtopology.utils as utils
import cimgraph.utils as cgutils

class TopologyMessage():

    def __init__(self) -> None:
        self.message = {}
        self.message['DistributionArea'] = {}
        self.message['DistributionArea']['mRID'] = ''
        self.message['DistributionArea']['Substations'] = []
        self.message['DistributionArea']['Feeders'] = []
        self.message['DistributionArea']['FeederAreas'] = []

    def get_context_from_feeder(self, feeder: cim.Feeder, connection: ConnectionInterface) -> None:

        feeder_model = FeederModel(container=feeder, connection=connection, distributed=True)
        cgutils.get_all_data(feeder_model)
        substation = feeder_model.get_from_triple(feeder, 'Feeder.NormalEnergizingSubstation')[0]
        distribution_area = feeder_model.get_from_triple(feeder, 'Feeder.DistributionArea')[0]
        feeder_area_model = feeder_model.distributed_areas[0]

        self.message['DistributionArea']['mRID'] = distribution_area.uri()
        self.message['DistributionArea']['Substations'].append(substation.uri())
        self.message['DistributionArea']['Feeders'].append(feeder.uri())

        msg = self.add_feeder_area(feeder_area_model)
        self.message['DistributionArea']['FeederAreas'].append(msg)


    def add_feeder_area(self, feeder_area_model: DistributedArea) -> dict:
        msg = {}
        feeder_area = feeder_area_model.container
        feeder = feeder_area_model.get_from_triple(feeder_area, 'FeederArea.Feeder')[0]

        msg['mRID'] = feeder_area.uri()
        msg['Feeder'] = feeder.uri()
        msg['AddressableEquipment'] = utils.identify_addressable(feeder_area_model, [])
        msg['UnaddressableEquipment'] = utils.identify_unaddressable(feeder_area_model, [])
        msg['Measurements'] = utils.identify_measurements(feeder_area_model, [])
        msg['SwitchAreas'] = []

        for switch_area_model in feeder_area_model.distributed_areas:
            sw_msg = self.add_switch_area(switch_area_model)
            msg['SwitchAreas'].append(sw_msg)

        return msg

        

    def add_switch_area(self, switch_area_model:DistributedArea) -> dict:
        sw_msg = {}
        switch_area = switch_area_model.container
        feeder_area = switch_area_model.get_from_triple(switch_area, 'SwitchArea.FeederArea')[0]

        sw_msg['mRID'] = switch_area.uri()
        sw_msg['FeederArea'] = feeder_area.uri()
        sw_msg['AddressableEquipment'] = utils.identify_addressable(switch_area_model, [])
        sw_msg['UnaddressableEquipment'] = utils.identify_unaddressable(switch_area_model, [])
        sw_msg['Measurements'] = utils.identify_measurements(switch_area_model, [])
        sw_msg['SecondaryAreas'] = []

        for secondary_area_model in switch_area_model.distributed_areas:
            sec_msg = self.add_secondary_area(secondary_area_model)
            sw_msg['SecondaryAreas'].append(sec_msg)

        return sw_msg

    def add_secondary_area(self, secondary_area_model: DistributedArea) -> dict:
        msg = {}
        secondary_area = secondary_area_model.container
        switch_area = secondary_area_model.get_from_triple(secondary_area, 'SecondaryArea.SwitchArea')[0]

        msg['mRID'] = secondary_area.uri()
        msg['Feeder'] = switch_area.uri()
        msg['AddressableEquipment'] = utils.identify_addressable(secondary_area_model, [])
        msg['UnaddressableEquipment'] = utils.identify_unaddressable(secondary_area_model, [])
        msg['Measurements'] = utils.identify_measurements(secondary_area_model, [])
        
        return msg
