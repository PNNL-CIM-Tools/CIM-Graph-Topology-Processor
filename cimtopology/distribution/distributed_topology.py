import logging

from cimgraph.models import DistributedArea
import cimgraph.data_profile.cimhub_ufls as cim #TODO: cleaner typing

_log = logging.getLogger(__name__)


def get_switch_classes(cim):
    """
    Returns list of switch CIM classes.

    Args:
        cim: The CIM profile module.

    Returns:
        list: List of switch classes from the CIM profile.
    """
    return [cim.Breaker, cim.Sectionaliser, cim.Recloser,
            cim.LoadBreakSwitch, cim.Switch]


def check_boundary(equipment: cim.ConductingEquipment, cim, switch_classes: list,
                   xfmr_boundary: bool) -> bool:
    """
    Checks if the given equipment is a boundary (switches or voltage-changing transformers).

    Args:
        equipment (cim.ConductingEquipment): The equipment to be checked.
        cim: The CIM profile module.
        switch_classes (list): List of switch CIM classes.
        xfmr_boundary (bool): Whether to check if transformers should be considered as boundaries.

    Returns:
        bool: True if the equipment is a boundary, False otherwise.
    """
    is_boundary = False
    # If equipment is a switch, then terminal is a boundary
    if equipment.__class__ in switch_classes:
        is_boundary = True
    # If asked to check transformers
    elif xfmr_boundary:
        # Then check if it is a PowerTransformer
        if isinstance(equipment, cim.PowerTransformer):
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


def add_to_area(equipment: cim.ConductingEquipment, container, dist_area: DistributedArea,
                contained_equipment: list, cim) -> None:
    """
    Adds a ConductingEquipment object to the current SubSchedulingArea and any
    Equipment that may be associated with the area but is not picked up by
    the topology trace.

    Args:
        equipment (cim.ConductingEquipment): The equipment to be added to the area.
        container: The scheduling area container.
        dist_area (DistributedArea): The distributed area model.
        contained_equipment (list): List to track contained equipment (mutated).
        cim: The CIM profile module.
    """
    contained_equipment.append(equipment)
    equipment.SubSchedulingArea = container
    dist_area.add_to_graph(equipment)
    if isinstance(equipment, cim.PowerTransformer):
        for tank in equipment.TransformerTanks:
            contained_equipment.append(tank)
            tank.SubSchedulingArea = container
            dist_area.add_to_graph(tank)
    elif isinstance(equipment, cim.PowerElectronicsConnection):
        for unit in equipment.PowerElectronicsUnit:
            contained_equipment.append(unit)
            unit.SubSchedulingArea = container
            dist_area.add_to_graph(unit)


def expand_to_boundaries(root_terminal: cim.Terminal, dist_area: DistributedArea,
                        container, cim, boundaries: list, parsed: list,
                        contained_equipment: list, switch_classes: list,
                        xfmr_boundary: bool = True):
    """
    Recursively expands topology from root terminal to boundaries.

    This function performs graph traversal of the CIM model, replacing the LinkNet logic
    of the original GridAPPS-D Topology Processor with direct CIM-Graph traversal.

    Args:
        root_terminal (cim.Terminal): The terminal from which to start the expansion.
        dist_area (DistributedArea): The distributed area model.
        container: The scheduling area container.
        cim: The CIM profile module.
        boundaries (list): List to accumulate boundary terminals (mutated).
        parsed (list): List to track visited identifiers (mutated).
        contained_equipment (list): List to track contained equipment (mutated).
        switch_classes (list): List of switch CIM classes.
        xfmr_boundary (bool, optional): Whether to consider transformers as boundaries. Defaults to True.
    """
    # Start at ConnectivityNode
    node = root_terminal.ConnectivityNode
    dist_area.add_to_graph(node)
    # Loop at all terminals associated with node
    for terminal in node.Terminals:
        if terminal.identifier not in parsed:
            # Get ConductingEquipment and determine if a boundary
            equipment = terminal.ConductingEquipment
            if equipment.identifier not in parsed:
#                parsed.append(equipment.identifier)
                is_boundary = check_boundary(equipment, cim, switch_classes, xfmr_boundary)
                # If not a boundary, then parse that equipment
                if not is_boundary:
                    # Assign the equipment to current SchedulingArea
                    add_to_area(equipment, container, dist_area, contained_equipment, cim)
                    # Expand topology through all terminals of next equipment
                    for next_terminal in equipment.Terminals:
                        if next_terminal.identifier not in parsed:
                            parsed.append(next_terminal.identifier)
                            expand_to_boundaries(next_terminal, dist_area, container, cim,
                                               boundaries, parsed, contained_equipment,
                                               switch_classes, xfmr_boundary)
                else:
                    # If equipment is a boundary, mark current terminal as boundary
                    boundaries.append(terminal)
                    terminal.BoundedSchedulingArea = container
                    if isinstance(equipment, cim.PowerTransformer):
                        add_to_area(equipment, container, dist_area, contained_equipment, cim) #exception for xfmrs

                    continue