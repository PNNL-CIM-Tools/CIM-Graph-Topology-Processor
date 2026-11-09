"""The voltage system of every bus, from a ``Network``, before any CIM model is built.

Moved from ``cimhub_core.topology`` (the walk and its rules are unchanged; its union-find islands are
now ``Topology.voltage_zones``). A caller describes its network (sources, branches that keep the
voltage, transformer coils) and ``walk`` gives each bus a ``BusSystem``: its BaseVoltage and whether
it is part of a 3-phase, single-phase or split-phase system.

Voltage zones are buses joined by branches (lines, switches open or closed, series elements). The walk
starts at the sources and crosses transformers zone by zone. The system of a zone the walk enters is
decided once, from every coil that lands on it:

1. a polyphase coil, or single-phase coils of two or more transformers on different conductors
   (a bank, a regulator bank, an open-delta pair): 3-phase;
2. otherwise a split-phase half: split-phase;
3. otherwise a single-phase transformer whose two coils have equal kV (a regulator) keeps the system
   it came from, so a single regulator on a lateral stays on the feeder's 3-phase system;
4. otherwise (a single-phase service or step-down): single-phase.

Its voltage is the source's ``kv`` on a source zone. Elsewhere it is the most common value the coils
landing there give (each coil's own kV in that system, never a ratio, so rounding does not accumulate);
on a tie, the coil the walk entered by. So a 13.09 kV substation secondary on a feeder of 7.2 kV
service primaries gives 12.47. Every coil on a zone must then be within ``NAMEPLATE_TOLERANCE`` of
its voltage (a nameplate off the system voltage is normal, e.g. a 66 kV winding on a 69 kV source) and
able to sit on its system, else the walk raises. That covers every transformer, so a later arrival at a
zone already entered needs no check of its own.

There is no snapping to a list of voltage bases (DSS ``CalcVoltageBases`` squashes a 240 V service
onto 208 V). ``BaseVoltage`` describes the as-operated voltage, so nearby computed values share one
object: ``nominal_kv`` rounds to 2 decimals in kV at 1 kV and above (12.4708 -> 12.47) and to whole
volts below (0.20785 -> 0.208). Ratings (``ratedU``) are never rounded.

Buses no source reaches are left out of the result; ``Topology.gaps`` reports them.
"""
from __future__ import annotations

import math
from collections import Counter, deque
from typing import NamedTuple

from cimtopology.core.network import Coil, Connection, Network, System, Topology, Transformer

_SQRT3 = math.sqrt(3)
NAMEPLATE_TOLERANCE = 0.1
"""How far a winding's kV may sit from the system voltage of a zone already reached (a tap range)."""


class BusSystem(NamedTuple):
    """One bus as the walk sees it."""

    kv: float
    """The system voltage, rounded by ``nominal_kv``: phase-to-phase on a 3-phase system, the coil
    voltage on a single-phase one, s1 to s2 on a split-phase one."""
    system: System

    @property
    def base_voltage(self) -> str:
        """mRID of the bus's BaseVoltage."""
        return base_voltage_mrid(self.kv)

    @property
    def three_phase(self) -> bool:
        """A phase-to-neutral coil here is rated phase-to-phase = coil voltage x sqrt(3)."""
        return self.system is System.THREE_PHASE


def nominal_kv(kv: float) -> float:
    """The BaseVoltage nominalVoltage (kV) for a computed bus voltage."""
    if kv <= 0:
        raise ValueError(f"a bus voltage must be positive, got {kv} kV")
    return round(kv, 2) if kv >= 1 else round(kv * 1000) / 1000


def base_voltage_mrid(kv: float) -> str:
    """``bv_12p47kv``, ``bv_208v``: the mRID of the BaseVoltage for ``nominal_kv(kv)``."""
    nominal = nominal_kv(kv)
    if nominal >= 1:
        return f"bv_{nominal:g}kv".replace(".", "p")
    return f"bv_{round(nominal * 1000)}v"


def system_kv(coil: Coil, system: System, *, transformer: str) -> float:
    """The system voltage a coil gives on its bus, before rounding."""
    match coil.connection, system:
        case Connection.POLYPHASE, System.THREE_PHASE:
            return coil.kv
        case Connection.PHASE_NEUTRAL, System.THREE_PHASE:
            return coil.kv * _SQRT3
        case Connection.PHASE_NEUTRAL, System.SINGLE_PHASE:
            return coil.kv
        case Connection.PHASE_PHASE, _:
            return coil.kv
        case Connection.HALF, System.SPLIT_PHASE:
            return 2 * coil.kv
    raise ValueError(f"Transformer {transformer}: a {coil.connection.value} coil on bus {coil.bus} "
                     f"cannot sit on a {system.value} system")


def walk(network: Network) -> dict[str, BusSystem]:
    """The ``BusSystem`` of every bus a source reaches."""
    zone_of = Topology(network).voltage_zones()
    landing: dict[str, list[tuple[Transformer, Coil]]] = {}
    for transformer in network.transformers:
        for coil in transformer.coils:
            landing.setdefault(zone_of[coil.bus], []).append((transformer, coil))

    systems: dict[str, BusSystem] = {}
    queue: deque[str] = deque()
    for source in network.sources:
        zone = zone_of[source.bus]
        _enter(systems, queue, landing.get(zone, []), zone, source.system, nominal_kv(source.kv),
               bus=source.bus, by="the source")
    while queue:
        near = queue.popleft()
        for transformer, near_coil in landing.get(near, []):
            for far_coil in transformer.coils:
                far = zone_of[far_coil.bus]
                if far == near or far in systems:
                    continue
                system = _far_system(landing[far], transformer, near_coil, far_coil, systems[near].system)
                kv = _common_kv(landing[far], system, entered_by=far_coil)
                _enter(systems, queue, landing[far], far, system, kv, bus=far_coil.bus,
                       by=f"Transformer {transformer.name}")
    return {bus: systems[zone] for bus, zone in zone_of.items() if zone in systems}


def _far_system(landing: list[tuple[Transformer, Coil]], transformer: Transformer, near_coil: Coil,
                far_coil: Coil, near_system: System) -> System:
    """The system of the zone ``far_coil`` lands on, by the rules in the module docstring."""
    connections = {coil.connection for _, coil in landing}
    if Connection.POLYPHASE in connections or _is_bank(landing):
        return System.THREE_PHASE
    if Connection.HALF in connections:
        return System.SPLIT_PHASE
    if len(transformer.coils) == 2 and math.isclose(near_coil.kv, far_coil.kv):
        return near_system
    return System.SINGLE_PHASE


def _is_bank(landing: list[tuple[Transformer, Coil]]) -> bool:
    """Single-phase coils of two or more transformers, on different conductors."""
    whole_coils = [(unit.name, coil.conductors) for unit, coil in landing
                   if coil.connection in (Connection.PHASE_NEUTRAL, Connection.PHASE_PHASE)]
    units = {name for name, _ in whole_coils}
    conductor_sets = {conductors for _, conductors in whole_coils}
    return len(units) > 1 and len(conductor_sets) > 1


def _common_kv(landing: list[tuple[Transformer, Coil]], system: System, *, entered_by: Coil) -> float:
    """The most common rounded voltage the coils on a zone give; on a tie, the coil the walk entered by."""
    kv_of = {id(coil): nominal_kv(system_kv(coil, system, transformer=unit.name)) for unit, coil in landing}
    counts = Counter(kv_of.values())
    most = max(counts.values())
    entered = kv_of[id(entered_by)]
    if counts[entered] == most:
        return entered
    return next(kv for kv, count in counts.items() if count == most)


def _enter(systems: dict[str, BusSystem], queue: deque[str], landing: list[tuple[Transformer, Coil]],
           zone: str, system: System, kv: float, *, bus: str, by: str) -> None:
    """Give a zone its system, after checking every coil on it against it."""
    known = systems.get(zone)
    if known is not None:  # a second source on the zone
        if known.system is not system or not math.isclose(known.kv, kv, rel_tol=NAMEPLATE_TOLERANCE):
            raise ValueError(f"{by} at bus {bus} is {kv} kV {system.value}, but its zone is already "
                             f"{known.kv} kV {known.system.value}")
        return
    for unit, coil in landing:
        coil_kv = system_kv(coil, system, transformer=unit.name)
        if not math.isclose(coil_kv, kv, rel_tol=NAMEPLATE_TOLERANCE):
            raise ValueError(f"Transformer {unit.name}: its coil on bus {coil.bus} gives {coil_kv:.6g} kV, "
                             f"but the island ({by} at bus {bus}) is {kv} kV {system.value}")
    systems[zone] = BusSystem(kv, system)
    queue.append(zone)
