from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cimgraph.models import DistributedArea

if TYPE_CHECKING:
    # Annotations only. The profile is never imported at runtime: every function
    # takes the live profile as its `cim` argument, sourced from `model.cim`, so the
    # module works against whichever profile the caller's model was built with.
    import cimgraph.data_profile.cimhub_2026 as cim

_log = logging.getLogger(__name__)


def get_switch_classes(cim):
    """The switch classes that bound a scheduling area.

    Deliberately an opt-in list of concrete classes, not `isinstance(x, cim.Switch)`.
    An area boundary has to be a point an ADMS can actually operate and that a utility
    treats as a normal open point, and several Switch subclasses are neither:

    * `Fuse` -- cutout fuses sit on every poletop transformer and overhead-to-
      underground cable drop. They are not normal open points, and no ADMS app can
      control one, so bounding an area at each of them would fragment a feeder into
      areas nobody can act on.
    * `Disconnector`, `EarthingSwitch`, `GroundDisconnector` -- isolation and grounding
      devices, operated for crew safety during a switching order, not for reconfiguring
      the network.
    * `Jumper` -- a temporary field connection, and zero-impedance besides.

    Note this list answers only the *area boundary* question. Bus merging
    (`bus_topology`) and island splitting (`feeder_island`) ask different questions
    about the same equipment and use their own rules: a fuse still merges the
    ConnectivityNodes on either side of it into one bus, and an open fuse still splits
    an island.
    """
    return [cim.Breaker, cim.Sectionaliser, cim.Recloser,
            cim.LoadBreakSwitch, cim.Switch]


def check_boundary(equipment: cim.ConductingEquipment, cim, switch_classes: list,
                   xfmr_boundary: bool) -> bool:
    """
    Checks if the given equipment is a boundary (switches or voltage-changing transformers).

    A transformer that steps voltage bounds an area; one whose windings share a rating is
    a voltage regulator and is crossed. Winding voltages are read from three sources in
    order of preference, because CIM models them differently across profiles and this
    ladder was hand-verified against multiple CIM100 variations:

    1. `PowerTransformerEnd.ratedU` on the transformer itself.
    2. `TransformerTank.TransformerTankInfo.TransformerEndInfos[].ratedU`, for
       tank-modelled transformers.
    3. `TransformerTank.Assets[].AssetInfo.TransformerEndInfos[].ratedU`, for older
       profiles that lack the `TransformerTankInfo` attribute and link through Asset.

    `found_voltages` is what makes this a ladder rather than a union: once a source
    yields ratings the later ones are skipped, so a profile that populates several does
    not mix them. With no source populated `is_boundary` stays True, which is the
    conservative answer -- a missed boundary silently merges two voltage levels into one
    area, which is worse than an extra boundary.

    Note the draft CIM18 transformer model replaces the CIM17 EndInfo associations
    entirely (TransformerWinding.ratedU, reached via TransformerLug/TankEnd), so sources
    2 and 3 are expected to become dead paths rather than gaining a fourth sibling.

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
                                voltages.append(_end_info_rated_u(end))
                                found_voltages = True
                            if len(set(voltages)) == 1:
                                is_boundary = False
                    # Older profiles do not have TransformeTankInfo attribute and link through Asset class.
                    # `Assets` itself was dropped in cimhub_2026, so guard the attribute the
                    # same way TransformerTankInfo is guarded above rather than assuming it.
                    if getattr(tank, 'Assets', None) is not None and not found_voltages:
                        for asset in tank.Assets:
                            if asset.AssetInfo is not None:
                                # If voltage rating of both windings are the same, not a boundary
                                for end in asset.AssetInfo.TransformerEndInfos:
                                    voltages.append(_end_info_rated_u(end))
                                    found_voltages = True
                                if len(set(voltages)) == 1:
                                    is_boundary = False

    return is_boundary


def _end_info_rated_u(end_info) -> float | None:
    """The rated voltage of a TransformerEndInfo, whichever name the profile gives it.

    CIM17 profiles call this `ratedU`, matching PowerTransformerEnd and
    TransformerTankEnd. cimhub_2026 renamed it to `ratedVoltage` on this class only, so
    reading `ratedU` unconditionally raises AttributeError against a 2026 model that
    populates TransformerTankInfo -- which real utility exports do on all of their tank
    transformers.

    Only the AssetInfo-side classes need this; the two end classes kept `ratedU`.
    """
    if hasattr(end_info, 'ratedU'):
        return end_info.ratedU
    return getattr(end_info, 'ratedVoltage', None)


def nest_area(area: cim.ConnectivityArea, parent: cim.ConnectivityArea) -> None:
    """Nest one scheduling area inside another.

    2026 collapsed FeederArea/SwitchArea/SecondaryArea/DistributionArea into a single
    ConnectivityArea distinguished by `areaType`, so the hierarchy that used to be
    encoded by class-specific associations (`SwitchArea.FeederArea`,
    `SecondaryArea.SwitchArea`) is now the generic ContainedWithin/ContainedAreas pair.
    """
    area.ContainedWithin = parent
    if area not in parent.ContainedAreas:
        parent.ContainedAreas.append(area)


def assign_to_area(equipment: cim.Equipment, area: cim.ConnectivityArea) -> None:
    """Record that a piece of equipment belongs to a scheduling area.

    cimhub_2026 replaced the old single-valued `Equipment.SubSchedulingArea` with
    `ConnectivityArea`, an EquipmentContainer reached through the many-valued
    `AdditionalEquipmentContainer`. Using the *additional* container matters:
    `EquipmentContainer` already holds the equipment's primary container (its Feeder
    or Substation), so writing there would erase feeder membership. Scheduling areas
    are an overlay on top of that, and equipment can sit in several nested ones.
    """
    if area not in equipment.AdditionalEquipmentContainer:
        equipment.AdditionalEquipmentContainer.append(area)
    if equipment not in area.AdditionalGroupedEquipment:
        area.AdditionalGroupedEquipment.append(equipment)


def mark_boundary(terminal: cim.Terminal, area: cim.ConnectivityArea) -> None:
    """Mark a Terminal as bounding a scheduling area.

    The Terminal side of the 2026 association is `BoundedConnectivityArea`, which is
    single-valued -- a terminal bounds one area -- unlike `assign_to_area` above.
    """
    terminal.BoundedConnectivityArea = area
    if terminal not in area.BoundaryTerminals:
        area.BoundaryTerminals.append(terminal)


def add_to_area(equipment: cim.ConductingEquipment, container, dist_area: DistributedArea,
                contained_equipment: list, cim) -> None:
    """
    Adds a ConductingEquipment object to the current ConnectivityArea and any
    Equipment that may be associated with the area but is not picked up by
    the topology trace.

    Args:
        equipment (cim.ConductingEquipment): The equipment to be added to the area.
        container: The scheduling area container (a cim.ConnectivityArea).
        dist_area (DistributedArea): The distributed area model.
        contained_equipment (list): List to track contained equipment (mutated).
        cim: The CIM profile module.
    """
    contained_equipment.append(equipment)
    assign_to_area(equipment, container)
    dist_area.add_to_graph(equipment)
    if isinstance(equipment, cim.PowerTransformer):
        for tank in equipment.TransformerTanks:
            contained_equipment.append(tank)
            assign_to_area(tank, container)
            dist_area.add_to_graph(tank)
    elif isinstance(equipment, cim.PowerElectronicsConnection):
        for unit in equipment.PowerElectronicsUnit:
            contained_equipment.append(unit)
            assign_to_area(unit, container)
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
                    mark_boundary(terminal, container)
                    if isinstance(equipment, cim.PowerTransformer):
                        add_to_area(equipment, container, dist_area, contained_equipment, cim) #exception for xfmrs

                    continue