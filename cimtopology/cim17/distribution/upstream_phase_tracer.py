import logging
import cimprofiles.cim17.cimhub_2023 as cim

_log = logging.getLogger(__name__)


def get_upstream_phase(conducting_equipment: cim.ConductingEquipment) -> cim.PhaseCode:
    """
    Traces upstream from a ConductingEquipment to find the high-side winding of a transformer
    and returns its OrderPhaseCodeKind.
    
    Args:
        conducting_equipment (cim.ConductingEquipment): The equipment to start tracing from
        
    Returns:
        cim.PhaseCode: The OrderPhaseCodeKind of the high-side transformer winding, or None if not found
    """
    if not conducting_equipment.Terminals:
        _log.warning(f"No terminals found for equipment {conducting_equipment.identifier}")
        return None
    
    # Get the first terminal
    first_terminal = conducting_equipment.Terminals[0]
    
    # Start the upstream trace
    visited_terminals = set()
    visited_equipment = set()
    
    return _trace_upstream_to_transformer(first_terminal, visited_terminals, visited_equipment)


def _trace_upstream_to_transformer(terminal: cim.Terminal, visited_terminals: set, visited_equipment: set) -> cim.PhaseCode:
    """
    Recursively traces upstream through the topology to find a transformer's high-side winding.
    
    Args:
        terminal (cim.Terminal): Current terminal being processed
        visited_terminals (set): Set of already visited terminal identifiers
        visited_equipment (set): Set of already visited equipment identifiers
        
    Returns:
        cim.PhaseCode: The OrderPhaseCodeKind of the high-side transformer winding, or None if not found
    """
    if terminal.identifier in visited_terminals:
        return None
    
    visited_terminals.add(terminal.identifier)
    
    # Get the connectivity node
    node = terminal.ConnectivityNode
    if not node:
        return None
    
    # Check all terminals connected to this node
    for connected_terminal in node.Terminals:
        if connected_terminal.identifier in visited_terminals:
            continue
            
        equipment = connected_terminal.ConductingEquipment
        if not equipment or equipment.identifier in visited_equipment:
            continue
            
        visited_equipment.add(equipment.identifier)
        
        # Check if this equipment is a PowerTransformer
        if isinstance(equipment, cim.PowerTransformer):
            # Found a transformer, now find the high-side winding
            high_side_phase = _get_high_side_phase(equipment)
            if high_side_phase:
                return high_side_phase
        
        # If not a transformer or switch (boundary), continue tracing upstream
        if not _is_boundary_equipment(equipment):
            # Continue tracing through all terminals of this equipment
            for next_terminal in equipment.Terminals:
                if next_terminal.identifier not in visited_terminals:
                    result = _trace_upstream_to_transformer(next_terminal, visited_terminals, visited_equipment)
                    if result:
                        return result
    
    return None


def _get_high_side_phase(transformer: cim.PowerTransformer) -> cim.PhaseCode:
    """
    Gets the OrderPhaseCodeKind from the high-side winding (sequenceNumber = 1) of a transformer.
    
    Args:
        transformer (cim.PowerTransformer): The transformer to analyze
        
    Returns:
        cim.PhaseCode: The OrderPhaseCodeKind of the high-side winding, or None if not found
    """
    # Check PowerTransformerEnd objects first
    if transformer.PowerTransformerEnd:
        for end in transformer.PowerTransformerEnd:
            if hasattr(end, 'sequenceNumber') and end.sequenceNumber == 1:
                # Found the high-side winding, get its phase information
                if hasattr(end, 'Terminal') and end.Terminal:
                    terminal = end.Terminal
                    if hasattr(terminal, 'phases'):
                        return terminal.phases
                # Alternative: check if the end itself has phase information
                if hasattr(end, 'phases'):
                    return end.phases
    
    # If PowerTransformerEnd doesn't have the info, check TransformerTanks
    if transformer.TransformerTanks:
        for tank in transformer.TransformerTanks:
            # Check if tank has TransformerTankInfo
            if hasattr(tank, 'TransformerTankInfo') and tank.TransformerTankInfo:
                tank_info = tank.TransformerTankInfo
                if hasattr(tank_info, 'TransformerEndInfos') and tank_info.TransformerEndInfos:
                    for end_info in tank_info.TransformerEndInfos:
                        if hasattr(end_info, 'sequenceNumber') and end_info.sequenceNumber == 1:
                            # Found high-side, look for phase information
                            if hasattr(end_info, 'phases'):
                                return end_info.phases
            
            # Alternative path through Assets (for older profiles)
            if hasattr(tank, 'Assets') and tank.Assets:
                for asset in tank.Assets:
                    if hasattr(asset, 'AssetInfo') and asset.AssetInfo:
                        asset_info = asset.AssetInfo
                        if hasattr(asset_info, 'TransformerEndInfos') and asset_info.TransformerEndInfos:
                            for end_info in asset_info.TransformerEndInfos:
                                if hasattr(end_info, 'sequenceNumber') and end_info.sequenceNumber == 1:
                                    if hasattr(end_info, 'phases'):
                                        return end_info.phases
    
    # If we can't find sequence number info, try to identify high-side by voltage
    # (highest voltage is typically the high-side)
    highest_voltage = 0
    high_side_phase = None
    
    if transformer.PowerTransformerEnd:
        for end in transformer.PowerTransformerEnd:
            if hasattr(end, 'ratedU') and end.ratedU > highest_voltage:
                highest_voltage = end.ratedU
                if hasattr(end, 'Terminal') and end.Terminal and hasattr(end.Terminal, 'phases'):
                    high_side_phase = end.Terminal.phases
                elif hasattr(end, 'phases'):
                    high_side_phase = end.phases
    
    return high_side_phase


def _is_boundary_equipment(equipment: cim.ConductingEquipment) -> bool:
    """
    Checks if equipment should be considered a boundary for upstream tracing.
    
    Args:
        equipment (cim.ConductingEquipment): Equipment to check
        
    Returns:
        bool: True if equipment is a boundary (switch), False otherwise
    """
    switch_classes = [cim.Breaker, cim.Sectionaliser, cim.Recloser, 
                     cim.LoadBreakSwitch, cim.Switch]
    
    return equipment.__class__ in switch_classes
