"""TopologicalIslands: buses joined through energized equipment, each with its angle reference."""
import pytest

from cimtopology.cim18 import build_topological_islands, build_topology


def _islands(model) -> list[tuple[int, str | None]]:
    """(bus count, angle reference mRID) per island, in the order they were built (largest first)."""
    return [(len(island.TopologicalNodes),
             None if island.AngleRefTopologicalNode is None else island.AngleRefTopologicalNode.mRID)
            for island in model.graph[model.cim.TopologicalIsland].values()]


def test_ieee13_is_one_island_referenced_at_the_source(ieee13):
    assert build_topology(ieee13) is None
    assert _islands(ieee13) == [(17, 'tn_sourcebus')]


def test_an_open_recloser_cuts_off_an_unreferenced_island(ieee13):
    ieee13.find_by_mRID('sw_rec1').open = True
    build_topology(ieee13)
    assert sorted(_islands(ieee13), key=str) == [(9, 'tn_sourcebus'), (9, None)]


def test_an_out_of_service_line_splits_an_island(ieee13):
    ieee13.find_by_mRID('ln_684611').inService = False
    build_topology(ieee13)
    assert _islands(ieee13) == [(16, 'tn_sourcebus'), (1, None)]


def test_switching_and_rebuilding_leaves_no_stale_islands(ieee13):
    cim = ieee13.cim
    recloser = ieee13.find_by_mRID('sw_rec1')
    recloser.open = True
    build_topology(ieee13)
    recloser.open = False
    build_topology(ieee13)
    assert _islands(ieee13) == [(17, 'tn_sourcebus')]
    [island] = ieee13.graph[cim.TopologicalIsland].values()
    assert all(bus.TopologicalIsland is island for bus in ieee13.graph[cim.TopologicalNode].values())


def test_islands_need_the_buses_first(ieee13):
    with pytest.raises(ValueError, match='build_topological_nodes first'):
        build_topological_islands(ieee13)


def test_node_breaker_islands(node_breaker):
    """The retained coupler is still closed, so it joins BB1 and BB2 into one island (though not one bus).
    The generator behind the open breaker is an island of its own, referenced at its machine."""
    build_topology(node_breaker)
    assert _islands(node_breaker) == [(4, 'tn_far'), (1, 'tn_g1')]
