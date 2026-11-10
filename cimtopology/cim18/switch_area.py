"""Switch areas: the feeder cut at its area-boundary switches (port of cim17 ``switch_area.py``).

Each area starts at a switch terminal that bounds no area yet and stops at area-boundary switches and
at transformers that change voltage (``boundaries.changes_voltage``). Regulators are crossed. Every
switch area is contained within the feeder area. They are found breadth first from the feeder area,
so upstream areas get the lower numbers, then from any switch the feeder does not reach.
Names follow GridAPPS-D: ``{feeder mRID}.{n}``.
"""
from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from cimtopology.cim18.areas import Cuts, create_area, fill_area, trace
from cimtopology.cim18.index import ModelIndex

if TYPE_CHECKING:
    from cimgraph.models import FeederModel


def create_switch_areas(feeder_model: FeederModel, index: ModelIndex, cuts: Cuts, feeder_area) -> list:
    cim = feeder_model.cim
    linknet = index.linknet
    areas = []
    pending = deque(feeder_area.BoundaryTerminal)
    # then every area-boundary switch, for the parts of the feeder no area reaches
    unreached = deque(terminal for number, terminal in enumerate(index.terminals[1:], start=1)
                      if cuts.switch[linknet.terminal_equipment[number]])
    while pending or unreached:
        boundary = pending.popleft() if pending else unreached.popleft()
        equipment = index.equipment_of(boundary.ConductingEquipment)
        if not cuts.switch[equipment]:
            continue                       # a transformer: secondary_area starts there
        for other in linknet.equipment_terminals[equipment]:
            start = index.terminals[other]
            if start.BoundedConnectedArea is not None:
                continue
            area = create_area(feeder_model, 'switchArea', f'{feeder_model.container.mRID}.{len(areas)}',
                               parent=feeder_area)
            found = trace(index, [index.node_of(start.ConnectivityNode)], stops_at=cuts.zone)
            fill_area(area, found, cim)
            areas.append(area)
            pending.extend(found.boundaries)
    return areas
