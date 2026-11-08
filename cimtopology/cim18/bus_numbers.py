"""Bus numbers and names for the TopologicalNodes of node-breaker substations.

Port of cim17 ``substation/bus_number_mapper.py``, with the same numbering. cim18v17 TopologicalNode has
native ``busNumber`` and ``busName``, so those are written in place of cim17's BusNameMarker and the
``aliasName`` it carried the number in.

Bus number: ``subregion * 100_000 + substation * 100 + voltage level * 10 + sequence``, each counted
from 1 in alphabetical order (voltage levels per substation, sequence per voltage level). When the
sequence or voltage level outgrows its digit, the number comes from a spillover range counting down
from 999997 (the top of the PSS/E range). Spillover is accepted: real bus numbers are assigned by the
ISO. Bus name: ``SUBSTATION_KV_SEQ``, at most 12 characters.

A bus is numbered from the BusbarSection on it (the first by name), else its first Junction. A bus
with neither, such as every bus of a feeder model, is left unnumbered.
"""
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from cimtopology.cim18.index import label

if TYPE_CHECKING:
    from cimgraph.models import GraphModel

_log = logging.getLogger(__name__)

TOP_BUS_NUMBER = 999997
NAME_LENGTH = 12


def number_buses(model: GraphModel) -> int:
    """Write busNumber and busName on every TopologicalNode with a busbar or junction; return the count."""
    cim = model.cim
    mapper = BusNumberMapper(model)
    numbered = 0
    for bus in model.graph.get(cim.TopologicalNode, {}).values():
        connector = _seed(bus, cim)
        if connector is None:
            continue
        bus.busNumber, bus.busName = mapper.number_and_name(connector)
        numbered += 1
    return numbered


def _seed(bus, cim):
    connectors = [terminal.ConductingEquipment for terminal in bus.Terminal]
    busbars = sorted((c for c in connectors if isinstance(c, cim.BusbarSection)), key=label)
    if busbars:
        return busbars[0]
    return next((c for c in connectors if isinstance(c, cim.Junction)), None)


class BusNumberMapper:
    """Numbers busbars by subregion, substation and voltage level (see the module docstring)."""

    def __init__(self, model: GraphModel):
        cim = model.cim
        substations = model.graph.get(cim.Substation, {}).values()
        self.substation_number = _alphabetical(substation.name for substation in substations)
        self.subregion_number = _alphabetical(substation.Region.name for substation in substations
                                              if substation.Region is not None)
        levels: dict[str, set[str]] = {}
        for level in model.graph.get(cim.VoltageLevel, {}).values():
            levels.setdefault(level.Substation.name, set()).add(level.name)
        self.level_number = {substation: _alphabetical(names) for substation, names in levels.items()}
        self.sequence: dict[tuple[int, int, int], int] = {}
        self.assigned: set[int] = set()
        self.spillover = TOP_BUS_NUMBER
        self.cim = cim

    def number_and_name(self, connector) -> tuple[int, str]:
        """The bus number and name for the bus a BusbarSection or Junction is on."""
        level = connector.EquipmentContainer
        if isinstance(level, self.cim.Bay):
            level = level.VoltageLevel
        if not isinstance(level, self.cim.VoltageLevel):
            raise ValueError(f"{type(connector).__name__} {label(connector)} is not in a VoltageLevel "
                             f"(its container is {type(level).__name__})")
        substation = level.Substation
        if substation.Region is None:
            raise ValueError(f"Substation {label(substation)} has no Region (SubGeographicalRegion)")
        key = (self.subregion_number[substation.Region.name], self.substation_number[substation.name],
               self.level_number[substation.name][level.name])
        sequence = self.sequence.get(key, 0) + 1
        self.sequence[key] = sequence
        subregion, station, level_number = key
        number = subregion * 100_000 + station * 100 + level_number * 10 + sequence
        if sequence > 9 or level_number > 9 or number > TOP_BUS_NUMBER or number in self.assigned:
            number = self._spill(connector)
        self.assigned.add(number)
        return number, _bus_name(substation.name, level, sequence)

    def _spill(self, connector) -> int:
        while self.spillover in self.assigned:
            self.spillover -= 1
        if self.spillover < 1:
            raise RuntimeError(f"no bus numbers left (1-{TOP_BUS_NUMBER})")
        number, self.spillover = self.spillover, self.spillover - 1
        _log.warning(f"bus number overflow for {label(connector)}: spillover bus {number}")
        return number


def _alphabetical(names) -> dict[str, int]:
    return {name: number for number, name in enumerate(sorted(set(names)), start=1)}


def _bus_name(substation_name: str, level, sequence: int) -> str:
    """``SUBSTATION_KV_SEQ``: the substation name cleaned and cut to fit 12 characters."""
    name = substation_name.upper()
    if 'STATION:' in name:
        name = name.split('STATION:')[1]
    name = re.sub(r'[^A-Z0-9]', '', name)
    kv = str(int(level.BaseVoltage.nominalVoltage.to('kV')))
    room = NAME_LENGTH - 2 - len(kv) - len(str(sequence))
    return f"{name[:max(1, room)]}_{kv}_{sequence}"
