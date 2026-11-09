"""The shared API on a small feeder with every case the operations have to handle.

    src --l1-- a --l2-- b --l3-- c          (trunk)
               |        |
               l4       sw (closed) -- d -- tie (open) -- e --l6-- f     (e, f fed from nowhere else)
               |
               x  =xf=  lv  (transformer)
    island --l7-- island2                    (no source: a gap)
    lonely                                   (declared, on no equipment: a gap)
    l5: a parallel second line a--b          (a link, not a loop worth reporting as a mesh)
"""
import csv

import pytest

from cimtopology.core import (Branch, Coil, Connection, Network, Source, System, Topology, Transformer,
                              write_linknet_csv, write_sorted_csv)

POLY = Connection.POLYPHASE
ABC = frozenset({1, 2, 3})
FEEDER = Network(
    sources=(Source('src', 12.47, System.THREE_PHASE),),
    branches=(
        Branch('l1', 'a', 'src'),          # written downstream first: sort must flip it
        Branch('l2', 'a', 'b'),
        Branch('l3', 'b', 'c'),
        Branch('l4', 'a', 'x'),
        Branch('l5', 'a', 'b'),
        Branch('sw', 'b', 'd', switch=True),
        Branch('tie', 'd', 'e', switch=True, open=True),
        Branch('l6', 'f', 'e'),
        Branch('l7', 'island', 'island2'),
    ),
    transformers=(Transformer('xf', (Coil('x', 12.47, POLY, ABC), Coil('lv', 0.48, POLY, ABC))),),
    nodes=('lonely',),
)


@pytest.fixture
def topology():
    return Topology(FEEDER)


def test_islands_split_at_the_open_switch(topology):
    islands = topology.islands()
    assert {bus for bus, root in islands.items() if root == 'src'} == {'src', 'a', 'b', 'c', 'x', 'lv', 'd'}
    assert islands['e'] == islands['f'] != 'src'
    assert islands['island'] == islands['island2']


def test_voltage_zones_cross_the_open_switch_but_not_the_transformer(topology):
    zones = topology.voltage_zones()
    assert zones['e'] == zones['src'] == zones['x']
    assert zones['lv'] != zones['x']


def test_sort_lists_every_branch_and_transformer_once(topology):
    rows = topology.sort()
    assert sorted(row.name for row in rows) == sorted(
        [branch.name for branch in FEEDER.branches] + [t.name for t in FEEDER.transformers])


def test_sort_orients_from_the_source(topology):
    rows = {row.name: row for row in topology.sort()}
    assert (rows['l1'].upstream, rows['l1'].downstream) == ('src', ('a',))
    assert (rows['xf'].upstream, rows['xf'].downstream) == ('x', ('lv',))
    assert rows['l1'].role == 'tree' and rows['l1'].energized and rows['l1'].root == 'src'


def test_sort_walks_the_source_side_first_then_dead_islands_then_open_switches(topology):
    rows = topology.sort()
    names = [row.name for row in rows]
    assert names[0] == 'l1'
    energized = [row.name for row in rows if row.energized and row.role != 'open']
    assert names[:len(energized)] == energized
    assert [row.name for row in rows if row.role == 'open'] == ['tie'] and names[-1] == 'tie'
    assert {row.name for row in rows if not row.energized and row.role != 'open'} == {'l6', 'l7'}


def test_sort_marks_the_parallel_line_as_a_link(topology):
    """a's list runs last parsed first (l5, l4, l2, l1), so l5 reaches b and l2 parallels it."""
    roles = {row.name: row.role for row in topology.sort()}
    assert [name for name, role in roles.items() if role == 'link'] == ['l2']


def test_gaps(topology):
    gaps = topology.gaps()
    assert gaps.isolated_nodes == ('lonely',)
    assert gaps.isolated_sources == ()
    assert sorted(map(sorted, gaps.unenergized)) == [['e', 'f'], ['island', 'island2']]


def test_a_source_on_no_equipment_is_a_gap():
    """The IEEE9500 SXST case: its source bus lost the reactor that connected it."""
    network = Network((Source('sourcebus', 115.0, System.THREE_PHASE),), (Branch('l', 'a', 'b'),), ())
    gaps = Topology(network).gaps()
    assert gaps.isolated_sources == ('sourcebus',)
    assert gaps.unenergized == (('a', 'b'),)


@pytest.mark.parametrize('branch, message', [
    (Branch('l', 'a', 'b', open=True), 'only a switch can be open'),
    (Branch('l', 'a', 'a'), "bus1 and bus2 are both 'a'"),
])
def test_bad_branches_fail(branch, message):
    with pytest.raises(ValueError, match=message):
        Topology(Network((), (branch,), ()))


def test_duplicate_names_fail():
    with pytest.raises(ValueError, match="'x' is already"):
        Topology(Network((), (Branch('x', 'a', 'b'), Branch('x', 'b', 'c')), ()))


def test_sorted_csv(topology, tmp_path):
    path = tmp_path / 'sorted.csv'
    write_sorted_csv(topology.sort(), path)
    rows = list(csv.DictReader(path.open()))
    assert rows[0] == {'order': '1', 'name': 'l1', 'upstream': 'src', 'downstream': 'a', 'role': 'tree',
                       'energized': 'true', 'root': 'src'}
    assert len(rows) == len(FEEDER.branches) + len(FEEDER.transformers)


def test_linknet_csv_matches_the_structure(topology, tmp_path):
    nodes_path, terminals_path = tmp_path / 'nodes.csv', tmp_path / 'terminals.csv'
    write_linknet_csv(topology.linknet, nodes_path, terminals_path)
    nodes = list(csv.DictReader(nodes_path.open()))
    terminals = list(csv.DictReader(terminals_path.open()))
    linknet = topology.linknet
    assert len(nodes) == linknet.node_count and len(terminals) == linknet.terminal_count
    assert nodes[0] == {'node': '1', 'name': 'src', 'last': str(linknet.last[1])}
    assert terminals[0] == {'term': '1', 'next': '0', 'far': str(linknet.node['src']),
                            'node': str(linknet.node['a']), 'equipment': 'l1'}
