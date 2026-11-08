"""The feeder area: from the feeder head to the first switches (port of cim17 ``feeder_area.py``).

Transformers are crossed, so the substation transformer is in the feeder area. Every area-boundary
switch on the feeder is a member of it, as in cim17 and CIMTBL-Models ``tier2_switch_delimited``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from cimtopology.cim18.areas import Cuts, create_area, fill_area, trace, add_member
from cimtopology.cim18.index import ModelIndex, label

if TYPE_CHECKING:
    from cimgraph.models import FeederModel


def head_terminals(feeder_model: FeederModel) -> list:
    """The feeder's NormalHeadTerminals (read from both sides) and every EnergySource terminal."""
    cim = feeder_model.cim
    feeder = feeder_model.container
    heads = list(feeder.NormalHeadTerminal)
    for terminal in feeder_model.graph.get(cim.Terminal, {}).values():
        if terminal.NormalHeadFeeder is feeder and not any(head is terminal for head in heads):
            heads.append(terminal)
    for source in feeder_model.graph.get(cim.EnergySource, {}).values():
        heads.extend(terminal for terminal in source.Terminals if not any(head is terminal for head in heads))
    return heads


def create_feeder_area(feeder_model: FeederModel, index: ModelIndex, cuts: Cuts):
    """The feeder area, holding everything up to the first area-boundary switches."""
    cim = feeder_model.cim
    feeder = feeder_model.container
    heads = head_terminals(feeder_model)
    if not heads:
        raise ValueError(f"Feeder {label(feeder)} has no NormalHeadTerminal and no EnergySource to start from")
    area = create_area(feeder_model, 'feederArea', label(feeder))
    found = trace(index, [index.node_of(terminal.ConnectivityNode) for terminal in heads], stops_at=cuts.switch)
    fill_area(area, found, cim)
    for number, equipment in enumerate(index.equipment[1:], start=1):
        if cuts.switch[number]:
            add_member(equipment, area, cim)
    return area
