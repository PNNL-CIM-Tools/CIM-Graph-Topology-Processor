from cimgraph.models import DistributedArea
# import cimgraph.data_profile.cimhub_2023 as cim

def identify_addressable(network: DistributedArea, 
                         equipment_uuid_list: list[str] = []) -> list[str]:
    cim = network.cim
    addressable_classes = [cim.Switch, cim.Breaker, cim.Disconnector,
        cim.Recloser, cim.LoadBreakSwitch, cim.Sectionaliser,
        cim.PowerElectronicsConnection, cim.PowerElectronicsUnit,
        cim.PhotovoltaicUnit, cim.BatteryUnit, cim.PowerElectronicsWindUnit,
        cim.RatioTapChanger, 
        cim.ShuntCompensator, cim.LinearShuntCompensator,
        cim.AsynchronousMachine, cim.SynchronousMachine]
    
    for class_type in addressable_classes:
        for equipment in network.graph.get(class_type, {}).values():
            equipment_uuid_list.append(equipment.uri())
    return equipment_uuid_list

def identify_unaddressable(network: DistributedArea, 
                         equipment_uuid_list: list[str] = []) -> list[str]:
    cim = network.cim
    unaddressable_classes = [cim.ACLineSegment, cim.Fuse,
        cim.PowerTransformer, cim.TransformerTank,
        cim.EnergySource, cim.EnergyConsumer]
    
    for class_type in unaddressable_classes:
        for equipment in network.graph.get(class_type, {}).values():
            equipment_uuid_list.append(equipment.uri())
    return equipment_uuid_list

def identify_measurements(network: DistributedArea, 
                         equipment_uuid_list: list[str] = []) -> list[str]:
    cim = network.cim
    unaddressable_classes = [cim.Measurement, cim.Analog, cim.Discrete]
    
    for class_type in unaddressable_classes:
        for equipment in network.graph.get(class_type, {}).values():
            equipment_uuid_list.append(equipment.uri())
    return equipment_uuid_list