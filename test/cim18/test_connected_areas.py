"""ConnectedAreas of IEEE13_CDPSM, checked against the hand-built tier2_switch_delimited model and
against the cim17 reference (``test/cim17/test_distribution_areas.py``).

cim17 gives IEEE13 4 switch areas: it crosses fuse1. Here fuse1 bounds an area (as it does in tier2),
so there are 5; the other four hold the same lines as cim17's.
"""
import pytest

from cimtopology.cim18 import build_connected_areas
from conftest import TIER2, load

LINES_AND_TRANSFORMERS = {
    ('feederArea', 'ieee13nodeckt'): {'sub3'},
    ('switchArea', 'fdr_ieee13nodeckt.0'): {'650632', '632633', '632645', '645646', 'reg1', 'reg2', 'reg3'},
    ('switchArea', 'fdr_ieee13nodeckt.1'): {'632670', '670671', '671680', '671684', '684652'},
    ('switchArea', 'fdr_ieee13nodeckt.2'): set(),          # xf1 only: fuse1 to xfm1
    ('switchArea', 'fdr_ieee13nodeckt.3'): {'692675'},
    ('switchArea', 'fdr_ieee13nodeckt.4'): {'684611'},
    ('secondaryArea', 'fdr_ieee13nodeckt.1.0'): {'tpoletop'},
    ('secondaryArea', 'fdr_ieee13nodeckt.2.0'): {'xfm1'},
}


def _areas(area):
    yield area
    for contained in area.ContainedArea:
        yield from _areas(contained)


def _lines_and_transformers(area, cim):
    return {equipment.name for equipment in area.AdditionalGroupedEquipment
            if isinstance(equipment, (cim.ACLineSegment, cim.PowerTransformer))}


def _membership(model) -> dict[str, list[str]]:
    """Equipment mRID -> the names of its additional containers, for every equipment."""
    cim = model.cim
    return {equipment.mRID: sorted(area.name for area in equipment.AdditionalEquipmentContainer)
            for cim_class, objects in model.graph.items() if issubclass(cim_class, cim.Equipment)
            for equipment in objects.values()}


def _switch_boundaries(model) -> list[tuple[str, list[str]]]:
    """(area kind, the switch terminals bounding it), one per area: the partition tier2 spells out."""
    cim = model.cim
    groups = []
    for area in model.graph[cim.ConnectedArea].values():
        terminals = sorted(t.mRID for t in area.BoundaryTerminal if isinstance(t.ConductingEquipment, cim.Switch))
        if terminals:
            groups.append((area.kind.name, terminals))
    return sorted(groups)


def test_area_tree(ieee13):
    cim = ieee13.cim
    feeder_area = build_connected_areas(ieee13)
    found = {(area.kind.name, area.name): _lines_and_transformers(area, cim) for area in _areas(feeder_area)}
    assert found == LINES_AND_TRANSFORMERS
    assert len(ieee13.graph[cim.ConnectedArea]) == len(LINES_AND_TRANSFORMERS)


def test_switch_terminals_bound_the_areas_tier2_gives_them(ieee13):
    """Each switch terminal bounds the area on its own side, grouped exactly as tier2 groups them."""
    build_connected_areas(ieee13)
    assert _switch_boundaries(ieee13) == _switch_boundaries(load(TIER2))


def test_transformer_terminals_bound_both_sides(ieee13):
    cim = ieee13.cim
    build_connected_areas(ieee13)
    terminals = ieee13.graph[cim.Terminal].values()
    bounded = {t.mRID: t.BoundedConnectedArea.name for t in terminals
               if t.BoundedConnectedArea is not None and isinstance(t.ConductingEquipment, cim.PowerTransformer)}
    assert bounded == {'xf_xfm1_T1': 'fdr_ieee13nodeckt.2', 'xf_xfm1_T2': 'fdr_ieee13nodeckt.2.0',
                       'xf_tpoletop_T1': 'fdr_ieee13nodeckt.1', 'xf_tpoletop_T2': 'fdr_ieee13nodeckt.1.0'}


def test_both_sides_of_every_association_are_written(ieee13):
    cim = ieee13.cim
    build_connected_areas(ieee13)
    for area in ieee13.graph[cim.ConnectedArea].values():
        assert all(any(c is area for c in e.AdditionalEquipmentContainer) for e in area.AdditionalGroupedEquipment)
        assert all(t.BoundedConnectedArea is area for t in area.BoundaryTerminal)
        assert all(contained.ContainedWithin is area for contained in area.ContainedArea)
    for terminal in ieee13.graph[cim.Terminal].values():
        if terminal.BoundedConnectedArea is not None:
            assert any(t is terminal for t in terminal.BoundedConnectedArea.BoundaryTerminal)


def test_containment(ieee13):
    feeder_area = build_connected_areas(ieee13)
    assert feeder_area.ContainedWithin is None
    for switch_area in feeder_area.ContainedArea:
        assert switch_area.kind.name == 'switchArea'
        assert all(secondary.name.startswith(switch_area.name + '.') for secondary in switch_area.ContainedArea)


def test_equipment_container_is_untouched(ieee13):
    cim = ieee13.cim
    before = {e.mRID: e.EquipmentContainer for cls, objs in ieee13.graph.items()
              if issubclass(cls, cim.Equipment) for e in objs.values()}
    build_connected_areas(ieee13)
    after = {e.mRID: e.EquipmentContainer for cls, objs in ieee13.graph.items()
             if issubclass(cls, cim.Equipment) for e in objs.values()}
    assert after == before


def test_rebuilding_gives_the_same_areas(ieee13):
    cim = ieee13.cim
    build_connected_areas(ieee13)
    first = _membership(ieee13), _switch_boundaries(ieee13)
    build_connected_areas(ieee13)
    assert (_membership(ieee13), _switch_boundaries(ieee13)) == first
    assert len(ieee13.graph[cim.ConnectedArea]) == len(LINES_AND_TRANSFORMERS)


def _kinds_of(model, name):
    [equipment] = [e for objs in model.graph.values() for e in objs.values()
                   if name in (getattr(e, 'name', None), getattr(e, 'mRID', None))]
    return {area.kind.name for area in equipment.AdditionalEquipmentContainer}


@pytest.mark.parametrize('equipment, kind', [
    ('sub3', 'feederArea'),          # transformers do not bound the feeder area (as cim17)
    ('brkr1', 'feederArea'),         # every area-boundary switch is in the feeder area (as cim17)
    ('reg1', 'switchArea'),          # equal end BaseVoltages: a regulator, crossed (as cim17)
    ('fuse1', 'feederArea'),         # CHANGED: cim17 crossed fuses and put fuse1 in a SwitchArea
    ('xfm1', 'secondaryArea'),       # 4.16 / 0.48 kV ends bound a secondary area (as cim17)
    ('tpoletop', 'secondaryArea'),   # 4.16 kV / 240 V ends; cim17 needed TransformerTankInfo for this
    ('pv_house_unit', 'secondaryArea'),  # a unit goes with its PowerElectronicsConnection
])
def test_key_equipment_placement(ieee13, equipment, kind):
    build_connected_areas(ieee13)
    assert _kinds_of(ieee13, equipment) == {kind}


def test_a_transformer_with_no_voltages_fails_the_build(ieee13):
    """cim17 took an unrated transformer for a regulator; now the build stops and names it."""
    cim = ieee13.cim
    [tpoletop] = [t for t in ieee13.graph[cim.PowerTransformer].values() if t.name == 'tpoletop']
    for end in tpoletop.PowerTransformerEnd:
        end.BaseVoltage = None
    tpoletop.TransformerTanks[0].TankConfiguration = None
    with pytest.raises(ValueError, match='tpoletop'):
        build_connected_areas(ieee13)
