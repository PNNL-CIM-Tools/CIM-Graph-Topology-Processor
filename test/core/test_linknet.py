"""LinkNet structure and spanning trees, checked against the papers in references/.

The golden case is Figure 8 of Anderson & Podmore 2022: the modified IEEE 13 bus feeder (meshed,
with an alternate source) and its last/next/far table. The equipment below is listed in the
paper's parse order (terminal pairs T1-T2, T3-T4, ...). Adding it in that order reproduces the
paper's node numbering 1-24, and each entry of the table checks the structure.
"""
import pytest

from cimtopology.core.linknet import NULL, LinkNet, spanning_forest

# (name, nodes of its terminals) in the order Figure 8 numbers the terminals
FIGURE_8_EQUIPMENT = [
    ('632633', ['632', '633']),            # T1, T2
    ('632670', ['632', '670']),            # T3, T4
    ('632645', ['632', '645']),            # T5, T6
    ('645646', ['645', '646']),            # T7, T8
    ('650632', ['650BRK', '632']),         # T9, T10
    ('670671', ['670', '671']),            # T11, T12
    ('671680', ['671', '680BRK']),         # T13, T14
    ('671684', ['671', '684']),            # T15, T16
    ('684611', ['684', '611']),            # T17, T18
    ('684652', ['684', '652']),            # T19, T20
    ('692675', ['692', '675']),            # T21, T22
    ('633635', ['633', '635']),            # T23, T24
    ('675636', ['675', '636']),            # T25, T26
    ('xfmr1', ['SOURCE', '650']),          # T27, T28
    ('reg1a', ['650', '650RG']),           # T29, T30
    ('reg1b', ['650', '650RG']),           # T31, T32
    ('reg1c', ['650', '650RG']),           # T33, T34
    ('xfmr1alt', ['ALT-SOURCE', '680']),   # T35, T36
    ('reg2a', ['680', '680RG']),           # T37, T38
    ('reg2b', ['680', '680RG']),           # T39, T40
    ('reg2c', ['680', '680RG']),           # T41, T42
    ('xfmr3', ['XF1', '634']),             # T43, T44
    ('tpoletop', ['670', 'HOUSE', 'HOUSE']),  # T45 (high side), T46, T47 (split-phase low side)
    ('gen1', ['636']),                     # T48
    ('pv_house', ['HOUSE']),               # T49
    ('battery634', ['634']),               # T50
]
FIGURE_8_NODES = ['632', '633', '670', '645', '646', '650BRK', '671', '680BRK', '684', '611', '652',
                  '692', '675', '635', '636', 'SOURCE', '650', '650RG', 'ALT-SOURCE', '680', '680RG',
                  'XF1', '634', 'HOUSE']
# Closed switches, merged as (first, second): fuse1, brkr1, swt1. sect1 and brkr2 are open.
FIGURE_8_CLOSED_SWITCHES = [('XF1', '633'), ('650RG', '650BRK'), ('692', '671')]

# Figure 8 table, Term -> (Next, Far), T1..T50
FIGURE_8_NEXT_FAR = {
    1: (0, 2), 2: (0, 1), 3: (1, 3), 4: (0, 1), 5: (3, 4), 6: (0, 1), 7: (6, 5), 8: (0, 4),
    9: (0, 1), 10: (5, 6), 11: (4, 7), 12: (0, 3), 13: (12, 8), 14: (0, 7), 15: (13, 9),
    16: (0, 7), 17: (16, 10), 18: (0, 9), 19: (17, 11), 20: (0, 9), 21: (15, 13), 22: (0, 12),
    23: (2, 14), 24: (0, 2), 25: (22, 15), 26: (0, 13), 27: (0, 17), 28: (0, 16), 29: (28, 18),
    30: (9, 17), 31: (29, 18), 32: (30, 17), 33: (31, 18), 34: (32, 17), 35: (0, 20), 36: (0, 19),
    37: (36, 21), 38: (0, 20), 39: (37, 21), 40: (38, 20), 41: (39, 21), 42: (40, 20),
    43: (23, 23), 44: (0, 22), 45: (11, 24), 46: (0, 3), 47: (46, 3), 48: (26, 15), 49: (47, 24),
    50: (44, 23),
}
# Figure 8 table, Name -> Last
FIGURE_8_LAST = {
    '632': 10, '633': 43, '670': 45, '645': 7, '646': 8, '650BRK': 34, '671': 15, '680BRK': 42,
    '684': 19, '611': 18, '652': 34, '692': 21, '675': 25, '635': 24, '636': 48, 'SOURCE': 27,
    '650': 33, '650RG': 34, 'ALT-SOURCE': 35, '680': 41, '680RG': 42, 'XF1': 43, '634': 50,
    'HOUSE': 49,
}
# Entries of the printed Last column that contradict its own Next/Far columns (as read from the
# figure). These are the values the structure gives, and the reason for each.
FIGURE_8_LAST_ERRATA = {
    '671': 21,     # swt1 merges 692 and 671: next(T21) = T15 puts 671's terminals on 692's list
    '680BRK': 14,  # its only terminal is T14 (far = 671); 42 is 680RG's, and brkr2 is open
    '652': 20,     # its only terminal is T20 (far = 684); 34 is 650RG's
}


def build(equipment=FIGURE_8_EQUIPMENT, closed=FIGURE_8_CLOSED_SWITCHES) -> LinkNet:
    linknet = LinkNet()
    for name, nodes in equipment:
        linknet.add_equipment(name, nodes)
    for first, second in closed:
        linknet.merge(linknet.node[first], linknet.node[second])
    return linknet


def test_figure_8_node_numbering():
    linknet = build()
    assert linknet.node_name[1:] == FIGURE_8_NODES
    assert linknet.terminal_count == 50


def test_figure_8_next_and_far():
    linknet = build()
    assert {t: (linknet.next[t], linknet.far[t]) for t in range(1, 51)} == FIGURE_8_NEXT_FAR


def test_figure_8_last():
    linknet = build()
    expected = FIGURE_8_LAST | FIGURE_8_LAST_ERRATA
    assert {name: linknet.last[linknet.node[name]] for name in FIGURE_8_NODES} == expected


def test_figure_8_sweep_from_633():
    """Every bus adjacent to 633 (CN2), through its merged list: 634 via XF1, 635, 632."""
    linknet = build()
    sweep = [(t, linknet.node_name[linknet.far[t]]) for t in linknet.terminals(linknet.node['633'])]
    assert sweep == [(43, '634'), (23, '635'), (2, '632')]


def test_far_is_own_node_for_one_terminal_devices():
    linknet = build()
    for name in ('gen1', 'pv_house', 'battery634'):
        [terminal] = linknet.equipment_terminals[linknet.equipment[name]]
        assert linknet.far[terminal] == linknet.terminal_node[terminal]


def test_three_winding_transformer_reaches_every_node():
    """The 2022 split-phase rule alone would leave the third winding's node unreachable."""
    linknet = LinkNet()
    linknet.add_equipment('sub3', ['sourcebus', '650', '650z'])
    forest = spanning_forest(linknet, [linknet.node['sourcebus']])
    assert set(forest.reached()) == {linknet.node[n] for n in ('sourcebus', '650', '650z')}


def _names(linknet, terminals):
    return [linknet.equipment_name[linknet.terminal_equipment[t]] for t in terminals]


def test_switch_delimited_areas_are_islands_of_the_unmerged_structure():
    """2022 V.C: without merging, each switch-delimited area is its own island."""
    linknet = build(closed=[])
    roots = list(range(1, linknet.node_count + 1))
    forest = spanning_forest(linknet, roots)
    areas = {}
    for node in forest.reached():
        areas.setdefault(forest.tree_of[node], set()).add(linknet.node_name[node])
    assert sorted(map(sorted, areas.values())) == sorted(map(sorted, [
        {'632', '633', '670', '645', '646', '650BRK', '671', '680BRK', '684', '611', '652', '635', 'HOUSE'},
        {'692', '675', '636'},
        {'SOURCE', '650', '650RG'},
        {'ALT-SOURCE', '680', '680RG'},
        {'XF1', '634'},
    ]))


def test_spanning_tree_from_source_labels_tree_and_link_branches():
    linknet = build()
    forest = spanning_forest(linknet, [linknet.node['SOURCE']])
    reached = {linknet.node_name[node] for node in forest.reached()}
    # brkr2 and sect1 are open: the ALT-SOURCE side and 636 beyond sect1 are reached only via swt1
    assert reached == set(FIGURE_8_NODES) - {'ALT-SOURCE', '680', '680RG'}
    # parallel regulator tanks: 650's list runs last parsed first, so reg1c is the tree branch
    # and reg1a, reg1b each close a loop with it
    assert sorted(_names(linknet, forest.links)) == ['reg1a', 'reg1b']
    # every tree branch's terminal is on its equipment, which touches the node it reached
    for node, terminal in enumerate(forest.tree):
        if terminal != NULL:
            equipment = linknet.terminal_equipment[terminal]
            touched = {linknet.terminal_node[t] for t in linknet.equipment_terminals[equipment]}
            assert set(linknet.members(node)) & touched


@pytest.mark.parametrize('depth_first', [False, True])
def test_order_emits_every_crossed_branch_once_oriented_from_the_source(depth_first):
    linknet = build()
    forest = spanning_forest(linknet, [linknet.node['SOURCE']], depth_first=depth_first)
    names = _names(linknet, forest.order)
    assert len(names) == len(set(names))
    first = {name: position for position, name in enumerate(names)}
    assert first['xfmr1'] == 0
    assert first['670671'] < first['671684'] < first['684611']   # a path is emitted root outward


def test_depth_first_emits_a_path_as_one_run():
    linknet = LinkNet()
    for name, nodes in [('trunk1', ['s', 'a']), ('lateral1', ['a', 'x']), ('trunk2', ['a', 'b']),
                        ('lateral2', ['x', 'y']), ('trunk3', ['b', 'c'])]:
        linknet.add_equipment(name, nodes)
    root = [linknet.node['s']]
    depth = _names(linknet, spanning_forest(linknet, root, depth_first=True).order)
    breadth = _names(linknet, spanning_forest(linknet, root).order)
    assert depth == ['trunk1', 'lateral1', 'lateral2', 'trunk2', 'trunk3']
    assert breadth == ['trunk1', 'trunk2', 'lateral1', 'trunk3', 'lateral2']


def test_crosses_stops_at_boundaries():
    linknet = build(closed=[])
    transformers = {linknet.equipment[n] for n in ('xfmr1', 'xfmr1alt', 'xfmr3', 'tpoletop')}
    forest = spanning_forest(linknet, [linknet.node['632']], crosses=lambda e: e not in transformers)
    assert 'HOUSE' not in {linknet.node_name[n] for n in forest.reached()}


def test_duplicate_equipment_fails():
    linknet = LinkNet()
    linknet.add_equipment('line', ['a', 'b'])
    with pytest.raises(ValueError, match="'line' is already"):
        linknet.add_equipment('line', ['b', 'c'])
