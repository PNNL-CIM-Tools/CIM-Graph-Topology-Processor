"""The voltage walk and BaseVoltage rounding, ported unchanged from cimhub_core/tests/test_topology.py.

Only the input changed: a ``Network`` with named ``Branch``es where cimhub_core took a ``BusGraph``
with ``ties`` as bus pairs.
"""
import math

import pytest

from cimtopology.core import (Branch, BusSystem, Coil, Connection, Network, Source, System, Transformer,
                              base_voltage_mrid, nominal_kv, walk)


@pytest.mark.parametrize("kv, nominal, mrid", [
    (7.2 * math.sqrt(3), 12.47, "bv_12p47kv"),
    (2.4 * math.sqrt(3), 4.16, "bv_4p16kv"),
    (115.0, 115.0, "bv_115kv"),
    (0.12 * math.sqrt(3), 0.208, "bv_208v"),
    (0.277 * math.sqrt(3), 0.48, "bv_480v"),
    (0.24, 0.24, "bv_240v"),
    (0.416, 0.416, "bv_416v"),
])
def test_nominal_kv_and_mrid(kv, nominal, mrid):
    assert nominal_kv(kv) == pytest.approx(nominal)
    assert base_voltage_mrid(kv) == mrid


def test_mismatched_bases_stay_apart():
    # the CalcVoltageBases problem: a 240 V service is not squashed onto 208 V
    assert base_voltage_mrid(0.24) != base_voltage_mrid(0.12 * math.sqrt(3))


def test_nominal_kv_rejects_non_positive():
    with pytest.raises(ValueError, match="must be positive"):
        nominal_kv(0.0)


# --- the walk -------------------------------------------------------------------------------------

THREE, SINGLE, SPLIT = System.THREE_PHASE, System.SINGLE_PHASE, System.SPLIT_PHASE
PN, PP, HALF, POLY = Connection.PHASE_NEUTRAL, Connection.PHASE_PHASE, Connection.HALF, Connection.POLYPHASE


def _unit(name, *coils):
    """A transformer from (bus, kv, connection, conductors) tuples."""
    return Transformer(name, tuple(Coil(bus, kv, connection, frozenset(conductors))
                                   for bus, kv, connection, conductors in coils))


def _walk(*transformers, ties=(("src", "feeder"),), source_kv=12.47):
    branches = tuple(Branch(f"tie{number}", bus1, bus2) for number, (bus1, bus2) in enumerate(ties))
    return walk(Network((Source("src", source_kv, THREE),), branches, transformers))


def test_ties_share_the_source_system():
    assert _walk()["feeder"] == BusSystem(12.47, THREE)


def test_three_phase_transformer_gives_its_own_kv():
    buses = _walk(_unit("t", ("feeder", 12.47, POLY, (1, 2, 3)), ("lv", 0.48, POLY, (1, 2, 3))))
    assert buses["lv"] == BusSystem(0.48, THREE) and buses["lv"].base_voltage == "bv_480v"


def test_service_starts_a_single_phase_system():
    buses = _walk(_unit("svc", ("feeder", 7.2, PN, (1,)), ("x", 0.24, PN, (1,))))
    assert buses["x"] == BusSystem(0.24, SINGLE) and not buses["x"].three_phase


def test_center_tap_starts_a_split_phase_system():
    buses = _walk(_unit("ct", ("feeder", 7.2, PN, (1,)), ("house", 0.12, HALF, (1,)), ("house", 0.12, HALF, (2,))))
    assert buses["house"] == BusSystem(0.24, SPLIT)


def test_bank_of_single_phase_units_is_three_phase():
    units = [_unit(f"t{phase}", ("feeder", 7.2, PN, (phase,)), ("lv", 0.277, PN, (phase,))) for phase in (1, 2, 3)]
    assert _walk(*units)["lv"] == BusSystem(0.48, THREE)


def test_open_delta_pair_is_three_phase():
    units = [_unit("a", ("feeder", 7.2, PN, (1,)), ("lv", 4.16, PP, (1, 2))),
             _unit("b", ("feeder", 7.2, PN, (2,)), ("lv", 4.16, PP, (2, 3)))]
    assert _walk(*units)["lv"] == BusSystem(4.16, THREE)


def test_single_regulator_keeps_the_feeder_system():
    # one regulator on a lateral: phase-to-neutral coil, equal kV, so the lateral stays 12.47 kV 3-phase
    buses = _walk(_unit("reg", ("feeder", 7.2, PN, (1,)), ("lateral", 7.2, PN, (1,))))
    assert buses["lateral"] == BusSystem(12.47, THREE)


def test_island_voltage_is_what_its_coils_agree_on():
    # a 13.09 kV substation secondary on a feeder of 7.2 kV service primaries (EPRI J1) is a 12.47 kV system
    services = [_unit(f"s{i}", ("feeder", 7.2, PN, (1,)), (f"x{i}", 0.24, PN, (1,))) for i in range(3)]
    buses = _walk(_unit("sub", ("src", 69.0, POLY, (1, 2, 3)), ("feeder", 13.09, POLY, (1, 2, 3))), *services,
                  ties=(), source_kv=69.0)
    assert buses["feeder"] == BusSystem(12.47, THREE) and buses["src"] == BusSystem(69.0, THREE)


def test_nameplate_within_tolerance_of_the_source():
    # a 66 kV winding on a 69 kV source (EPRI K1)
    buses = _walk(_unit("t2", ("src", 66.0, POLY, (1, 2, 3)), ("lv", 13.8, POLY, (1, 2, 3))), ties=(), source_kv=69.0)
    assert buses["lv"] == BusSystem(13.8, THREE)


def test_coil_off_the_island_voltage_raises():
    with pytest.raises(ValueError, match=r"Transformer t: its coil on bus feeder gives 4.16 kV, but the island"):
        _walk(_unit("t", ("feeder", 4.16, POLY, (1, 2, 3)), ("lv", 0.48, POLY, (1, 2, 3))))


def test_half_coil_on_a_three_phase_island_raises():
    with pytest.raises(ValueError, match="a half coil on bus feeder cannot sit on a 3-phase system"):
        _walk(_unit("ct", ("feeder", 0.12, HALF, (1,)), ("x", 7.2, PN, (1,))))


def test_buses_no_source_reaches_are_left_out():
    buses = _walk(ties=(("src", "feeder"), ("island_a", "island_b")))
    assert "island_a" not in buses and "feeder" in buses


def test_an_open_switch_keeps_its_voltage():
    """New with branches: a voltage zone runs through an open switch (bus_graph.py's rule)."""
    network = Network((Source("src", 12.47, THREE),),
                      (Branch("line", "src", "a"), Branch("tie", "a", "b", switch=True, open=True)), ())
    assert walk(network)["b"] == BusSystem(12.47, THREE)
