"""Secondary areas: the low-voltage side of each voltage-changing transformer (port of cim17
``secondary_area.py``).

A switch area's boundary terminals include those of the transformers that change voltage
(``boundaries.changes_voltage``). Each other terminal of such a transformer that bounds no area yet
starts a secondary area, contained within that switch area, with the same stops as a switch area.
The transformer is a member of its secondary areas. Names follow GridAPPS-D: ``{switch area}.{n}``.

Unlike cim17, building a secondary area leaves its switch area's boundaries alone (cim17 overwrote
``switch_area_model.boundaries`` with the secondary area's own while looping over them).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from cimtopology.cim18.areas import Cuts, add_member, create_area, fill_area, trace
from cimtopology.cim18.index import ModelIndex

if TYPE_CHECKING:
    from cimgraph.models import FeederModel


def create_secondary_areas(feeder_model: FeederModel, index: ModelIndex, cuts: Cuts, switch_area) -> list:
    cim = feeder_model.cim
    linknet = index.linknet
    areas = []
    for boundary in list(switch_area.BoundaryTerminal):
        equipment = index.equipment_of(boundary.ConductingEquipment)
        if not cuts.step[equipment]:
            continue
        for other in linknet.equipment_terminals[equipment]:
            start = index.terminals[other]
            if start.BoundedConnectedArea is not None:
                continue
            area = create_area(feeder_model, 'secondaryArea', f'{switch_area.name}.{len(areas)}',
                               parent=switch_area)
            fill_area(area, trace(index, [index.node_of(start.ConnectivityNode)], stops_at=cuts.zone), cim)
            add_member(boundary.ConductingEquipment, area, cim)
            areas.append(area)
    return areas
