import logging

from cimgraph.models import DistributedArea
from cimgraph.databases import ConnectionInterface
import cimgraph.data_profile.cimhub_2023 as cim #TODO: cleaner typing

_log = logging.getLogger(__name__)


class DistributedTopology():

    def __init__(self, DistArea: DistributedArea):
        self.DistArea = DistArea
        self.cim = DistArea.cim
        self.container = DistArea.container
        self.boundaries = []
        self.parsed = []
        self.contained_equipment = []
        self.switch_classes = [self.cim.Breaker, self.cim.Sectionaliser,
                               self.cim.Recloser, self.cim.LoadBreakSwitch, self.cim.Switch]
        

    def check_boundary(self, equipment: cim.ConductingEquipment, xfmr_boundary:bool) -> bool:
        is_boundary = False
        
        if equipment.__class__ in self.switch_classes:
            is_boundary = True

        elif xfmr_boundary:
            if equipment.__class__ == cim.PowerTransformer:
                found_voltages = False
                is_boundary = True
                voltages = []

                if equipment.PowerTransformerEnd is not None:
                    for end in equipment.PowerTransformerEnd:
                        voltages.append(end.ratedU)
                        found_voltages = True
                    if len(set(voltages)) == 1:
                        is_boundary = False

                if equipment.TransformerTanks is not None and not found_voltages:
                    for tank in equipment.TransformerTanks:
                        if 'TransformerTankInfo' in cim.TransformerTank.__dataclass_fields__.keys():
                            if tank.TransformerTankInfo is not None:
                                # Iterate through xfmr ends to get winding voltage
                                for end in tank.TransformerTankInfo.TransformerEndInfos:
                                    voltages.append(end.ratedU)
                                    found_voltages = True
                                if len(set(voltages)) == 1:
                                    is_boundary = False

                        if tank.Assets is not None and not found_voltages:
                            for asset in tank.Assets:
                                if asset.AssetInfo is not None:
                                    for end in asset.AssetInfo.TransformerEndInfos:
                                        voltages.append(end.ratedU)
                                        found_voltages = True
                                    if len(set(voltages)) == 1:
                                        is_boundary = False
            
        return is_boundary


    def expand_to_boundaries(self, root_terminal:cim.Terminal, xfmr_boundary:bool = True):

        node = root_terminal.ConnectivityNode
        self.DistArea.add_to_graph(node)
        for terminal in node.Terminals:
            if terminal.identifier not in self.parsed:
                equipment = terminal.ConductingEquipment
                if equipment.identifier not in self.parsed:
                    # self.parsed.append(equipment.identifier)
                    is_boundary = self.check_boundary(equipment, xfmr_boundary)
                    if not is_boundary:
                        self.contained_equipment.append(equipment)
                        equipment.ResourceContainer = self.container
                        self.DistArea.add_to_graph(equipment)
                        for next_terminal in equipment.Terminals:
                            if next_terminal.identifier not in self.parsed:
                                self.parsed.append(next_terminal.identifier)
                                self.expand_to_boundaries(next_terminal, xfmr_boundary)
                    else:
                        self.boundaries.append(terminal)
                        terminal.BoundedResourceContainer = self.container
                        continue
