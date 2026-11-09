"""Characterization tests for the frozen CIM17 distribution topology (cimtopology.cim17).

``ieee13_distributed.xml`` ships the areas the GridAPPS-D topology processor built for IEEE13.
Each test strips them, rebuilds them with ``create_distributed_feeder``, and checks that the result
matches what the file shipped: the same areas, holding the same equipment, bounded by the same
terminals. These tests pin the behavior that the CIM18 rewrite must reproduce or deliberately change.
"""
from pathlib import Path

import pytest

MODEL = Path(__file__).parents[1] / 'test_models' / 'ieee13_distributed.xml'


def _area_classes(cim):
    return [cim.FeederArea, cim.SwitchArea, cim.SecondaryArea]


def _membership(network, cim) -> dict[tuple[str, str], list[str]]:
    """(area class, area name) -> sorted names of the equipment whose SubSchedulingArea is that area."""
    members = {}
    for area_class in _area_classes(cim):
        for area in network.graph.get(area_class, {}).values():
            members[(area_class.__name__, area.name)] = sorted(
                equipment.name
                for cim_class in network.graph
                for equipment in network.graph[cim_class].values()
                if getattr(equipment, 'SubSchedulingArea', None) is area)
    return members


def _bounded_terminals(network, cim) -> dict[str, str]:
    """Terminal name -> name of the area it bounds."""
    return {terminal.name: terminal.BoundedSchedulingArea.name
            for terminal in network.graph[cim.Terminal].values()
            if terminal.BoundedSchedulingArea is not None}


def _strip_areas(network, cim) -> None:
    """Remove every area the file shipped, so the rebuild starts from a bare feeder."""
    for area_class in _area_classes(cim) + [cim.DistributionArea]:
        network.graph.pop(area_class, None)
    for cim_class in network.graph:
        if 'SubSchedulingArea' in cim_class.__dataclass_fields__:
            for equipment in network.graph[cim_class].values():
                equipment.SubSchedulingArea = None
    for terminal in network.graph[cim.Terminal].values():
        terminal.BoundedSchedulingArea = None


@pytest.fixture(scope='module')
def ieee13():
    """(reference membership, reference boundaries, rebuilt network, cim)."""
    with pytest.MonkeyPatch.context() as env:
        env.setenv('CIMG_CIM_PROFILE', 'cimhub_2023')
        env.setenv('CIMG_NAMESPACE', 'http://iec.ch/TC57/CIM100#')
        from cimgraph.core.env_vars import get_cim_profile
        get_cim_profile.cache_clear()
        from cimgraph.databases import XMLFile
        from cimgraph.models import FeederModel
        from cimtopology.cim17.distribution import create_distributed_feeder

        connection = XMLFile(filename=str(MODEL))
        cim = connection.cim
        loader = FeederModel(connection=connection, container=cim.Feeder(), distributed=False)
        [feeder] = loader.graph[cim.Feeder].values()
        network = FeederModel(connection=connection, container=feeder, distributed=False)

        reference = _membership(network, cim)
        reference_boundaries = _bounded_terminals(network, cim)
        _strip_areas(network, cim)
        create_distributed_feeder(network)
        get_cim_profile.cache_clear()
        return reference, reference_boundaries, network, cim


def test_reference_fixture_shape(ieee13):
    reference, boundaries, _, _ = ieee13
    counts = {}
    for area_class, _name in reference:
        counts[area_class] = counts.get(area_class, 0) + 1
    assert counts == {'FeederArea': 1, 'SwitchArea': 4, 'SecondaryArea': 2}
    assert len(boundaries) == 13


def test_rebuild_matches_reference_membership(ieee13):
    reference, _, network, cim = ieee13
    assert _membership(network, cim) == reference


def test_rebuild_matches_reference_boundaries(ieee13):
    _, reference_boundaries, network, cim = ieee13
    assert _bounded_terminals(network, cim) == reference_boundaries


def _area_of(members: dict, equipment_name: str) -> set[str]:
    return {area_class for (area_class, _), names in members.items() if equipment_name in names}


@pytest.mark.parametrize('equipment, area_class', [
    ('sub3', 'FeederArea'),         # transformers do not bound the feeder area (xfmr_boundary=False)
    ('brkr1', 'FeederArea'),        # every switch is put in the feeder area up front
    ('Reg', 'SwitchArea'),          # equal winding ratings: a regulator, crossed
    ('reg1', 'SwitchArea'),         # ... and its tanks go with it
    ('fuse1', 'SwitchArea'),        # Fuse is not a switch class: crossed, not a boundary
    ('xfm1', 'SecondaryArea'),      # 4.16 / 0.48 kV: bounds a secondary area
    ('tpoletop', 'SecondaryArea'),  # rated through TransformerTankInfo in CIM17 data
])
def test_key_equipment_placement(ieee13, equipment, area_class):
    _, _, network, cim = ieee13
    assert _area_of(_membership(network, cim), equipment) == {area_class}
