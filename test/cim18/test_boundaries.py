"""The two area-boundary predicates, on hand-built cim18v17 objects."""
import pytest

import cimprofiles.cim18.cim18v17 as cim
from cimtopology.cim18.boundaries import bounds_switch_area, changes_voltage


def _kv(value):
    return cim.Voltage(value, 'kV')


def _base(kv):
    return cim.BaseVoltage(nominalVoltage=_kv(kv))


def _transformer(*ends, windings=()):
    """A PowerTransformer from (BaseVoltage kV, ratedU kV) pairs, and tank windings' ratedU kV."""
    transformer = cim.PowerTransformer(name='t')
    for base, rated in ends:
        end = cim.PowerTransformerEnd(BaseVoltage=None if base is None else _base(base),
                                      ratedU=None if rated is None else _kv(rated), PowerTransformer=transformer)
        transformer.PowerTransformerEnd.append(end)
    if windings:
        configuration = cim.TransformerTankConfiguration()
        for rated in windings:
            configuration.TransformerWinding.append(cim.TransformerWinding(ratedU=_kv(rated)))
        tank = cim.TransformerTank(PowerTransformer=transformer, TankConfiguration=configuration)
        transformer.TransformerTanks.append(tank)
    return transformer


# --- bounds_switch_area: changed from cim17 -----------------------------------------------------

@pytest.mark.parametrize('switch_class', [cim.Breaker, cim.Recloser, cim.Sectionaliser, cim.LoadBreakSwitch,
                                          cim.Switch, cim.Fuse, cim.Disconnector, cim.Cut])
def test_every_switch_but_a_jumper_bounds(switch_class):
    """cim17 crossed Fuse and Disconnector; IEEE13 gains a switch area at fuse1 (as tier2 has)."""
    assert bounds_switch_area(switch_class(name='s'), cim)


def test_a_jumper_is_crossed():
    assert not bounds_switch_area(cim.Jumper(name='j'), cim)


@pytest.mark.parametrize('switch, expected', [
    (cim.Breaker(name='b', areaBoundary=False), False),
    (cim.Jumper(name='j', areaBoundary=True), True),
])
def test_area_boundary_overrides_the_class(switch, expected):
    assert bounds_switch_area(switch, cim) is expected


def test_only_switches_bound():
    assert not bounds_switch_area(cim.ACLineSegment(name='l'), cim)


# --- changes_voltage: the secondary-area definition ---------------------------------------------

def test_end_base_voltages_decide_first():
    """xfm1: 4.16 / 0.48 kV ends."""
    assert changes_voltage(_transformer((4.16, 4.16), (0.48, 0.48)), cim)


def test_a_regulator_has_one_base_voltage():
    """reg1: both ends on bv_4p16kv. The ratings agree too (2.4 kV), but BaseVoltage decides."""
    assert not changes_voltage(_transformer((4.16, 2.4), (4.16, 2.4)), cim)


def test_base_voltage_wins_over_ratings():
    """A tap-off nameplate on one system voltage: equal bases, unequal ratings, so a regulator."""
    assert not changes_voltage(_transformer((4.16, 4.16), (4.16, 4.0)), cim)


def test_ratings_when_an_end_has_no_base_voltage():
    assert changes_voltage(_transformer((4.16, 4.16), (None, 0.48)), cim)


def test_tank_windings_when_the_ends_carry_neither():
    """tpoletop in a file whose ends carry no BaseVoltage: the ratings are on its TankConfiguration."""
    assert changes_voltage(_transformer((None, None), (None, None), windings=(4.16, 0.24, 0.24)), cim)


def test_nothing_to_compare_raises():
    """cim17 read this as a regulator (None == None)."""
    with pytest.raises(ValueError, match='cannot be told from a regulator'):
        changes_voltage(_transformer((None, None), (None, None)), cim)


def test_an_autotransformer_uses_its_ends():
    """AutoTransformer is not a PowerTransformer subclass, but it follows the same ladder."""
    auto = cim.AutoTransformer(name='a')
    for kv in (13.8, 12.47):
        auto.AutoTransformerEnd.append(cim.AutoTransformerEnd(BaseVoltage=_base(kv), AutoTransformer=auto))
    assert changes_voltage(auto, cim)
