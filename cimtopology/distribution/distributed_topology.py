import logging

from cimgraph.models import DistributedArea
import cimgraph.data_profile.cimhub_2023 as cim #TODO: cleaner typing

_log = logging.getLogger(__name__)


class DistributedTopology():
    """
    Class to handle the topology of a distributed area in a CIM model.

    This class builds and traces the topology of a distributed area, identifies
    boundaries, and expands the topology to include all related equipment and terminals.

    This class replaces the LinkNet logic of the original GridAPPS-D Topology Processor
    with direct graph traversal of the CIM-Graph FeederModel
    """

    def __init__(self, DistArea: DistributedArea):
        """
        Initializes the DistributedTopology with the given distributed area model.

        Args:
            DistArea (DistributedArea): The distributed area model to be managed.
        """
        self.DistArea = DistArea
        self.cim = DistArea.cim
        self.container = DistArea.container
        self.boundaries = []
        self.parsed = []
        self.contained_equipment = []
        self.switch_classes = [self.cim.Breaker, self.cim.Sectionaliser,
                               self.cim.Recloser, self.cim.LoadBreakSwitch, self.cim.Switch]
        

    def check_boundary(self, equipment: cim.ConductingEquipment, xfmr_boundary:bool) -> bool:
        """
        Checks if the given equipment is a boundary.

        Args:
            equipment (cim.ConductingEquipment): The equipment to be checked.
            xfmr_boundary (bool): Whether to check if transformers should be considered as boundaries.

        Returns:
            bool: True if the equipment is a boundary, False otherwise.
        """
        is_boundary = False
        # If equipment is a switch, then terminal is a boundary
        if equipment.__class__ in self.switch_classes:
            is_boundary = True
        # If asked to check transformers
        elif xfmr_boundary:
            # Then check if it is a PowerTransformer
            if equipment.__class__ == cim.PowerTransformer:
                found_voltages = False
                is_boundary = True
                voltages = []
                # Now determine if it is a voltage regulator. 
                # If voltage rating of both windings are the same, not a boundary
                if equipment.PowerTransformerEnd is not None:
                    for end in equipment.PowerTransformerEnd:
                        voltages.append(end.ratedU)
                        found_voltages = True
                    if len(set(voltages)) == 1:
                        is_boundary = False
                # If that logic did not work, then loop through the Tanks
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
                        # Older profiles do not have TransformeTankInfo attribute and link through Asset class
                        if tank.Assets is not None and not found_voltages:
                            for asset in tank.Assets:
                                if asset.AssetInfo is not None:
                                    # If voltage rating of both windings are the same, not a boundary
                                    for end in asset.AssetInfo.TransformerEndInfos:
                                        voltages.append(end.ratedU)
                                        found_voltages = True
                                    if len(set(voltages)) == 1:
                                        is_boundary = False
            
        return is_boundary


    def expand_to_boundaries(self, root_terminal:cim.Terminal, xfmr_boundary:bool = True):
        """
        Expands the topology from the root terminal to identify boundaries and include related equipment.

        Args:
            root_terminal (cim.Terminal): The terminal from which to start the expansion.
            xfmr_boundary (bool, optional): Whether to consider transformers as boundaries. Defaults to True.
        """
        # Start at ConnectivityNode
        node = root_terminal.ConnectivityNode
        self.DistArea.add_to_graph(node)
        # Loop at all terminals associated with node
        for terminal in node.Terminals:
            if terminal.identifier not in self.parsed:
                # Get ConductingEquipment and determine if a boundary
                equipment = terminal.ConductingEquipment
                if equipment.identifier not in self.parsed:
#                    self.parsed.append(equipment.identifier)
                    is_boundary = self.check_boundary(equipment, xfmr_boundary)
                    # If not a boundary, then parse that equipment
                    if not is_boundary:
                        # Assign the equipment to current ResourceContainer
                        self.contained_equipment.append(equipment)
                        equipment.ResourceContainer = self.container
                        self.DistArea.add_to_graph(equipment)
                        # Expand topology through all terminals of next equipment
                        for next_terminal in equipment.Terminals:
                            if next_terminal.identifier not in self.parsed:
                                self.parsed.append(next_terminal.identifier)
                                self.expand_to_boundaries(next_terminal, xfmr_boundary)
                    else:
                        # If equipment is a boundary, mark current terminal as boundary
                        self.boundaries.append(terminal)
                        terminal.BoundedResourceContainer = self.container
                        continue
