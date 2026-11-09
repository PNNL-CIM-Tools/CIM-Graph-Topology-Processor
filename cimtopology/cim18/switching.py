"""Switch state and service state, read the same way by the bus and island builders.

- A switch is open per ``Switch.open``, falling back to ``normalOpen``; with neither it is closed
  (as cim17 read it).
- A bus tie (IEC 61970-301 TopologicalNode rule) is a closed switch that is not ``retained``.
  ``retained=None`` is not retained: in real data it marks only series-capacitor bypass breakers.
- Equipment is in service per ``inService``, falling back to ``normallyInService``; with neither it is
  in service.
"""
from __future__ import annotations


def is_open(switch) -> bool:
    state = switch.open if switch.open is not None else switch.normalOpen
    return bool(state)


def is_bus_tie(equipment, cim) -> bool:
    """A zero-impedance connection that merges two ConnectivityNodes into one TopologicalNode."""
    return isinstance(equipment, cim.Switch) and not equipment.retained and not is_open(equipment)


def in_service(equipment) -> bool:
    state = equipment.inService if equipment.inService is not None else equipment.normallyInService
    return state is not False


def energizes(equipment, cim) -> bool:
    """Equipment an island crosses: in service and, for a switch, closed."""
    return in_service(equipment) and not (isinstance(equipment, cim.Switch) and is_open(equipment))
