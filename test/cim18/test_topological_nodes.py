"""TopologicalNodes (IEC 61970-301: closed, non-retained switches merge) and bus numbers."""
import pytest

from cimtopology.cim18 import build_topological_nodes, number_buses


def _buses(model) -> list[list[str]]:
    """Each TopologicalNode as the sorted mRIDs of its ConnectivityNodes."""
    return sorted(sorted(node.mRID for node in bus.ConnectivityNodes)
                  for bus in model.graph[model.cim.TopologicalNode].values())


def _equipment(model, mrid):
    return model.find_by_mRID(mrid)


# --- IEEE13_CDPSM ------------------------------------------------------------------------------

def test_ieee13_closed_switches_merge_their_nodes(ieee13):
    build_topological_nodes(ieee13)
    buses = _buses(ieee13)
    assert len(ieee13.graph[ieee13.cim.ConnectivityNode]) == 22 and len(buses) == 17
    merged = [bus for bus in buses if len(bus) > 1]
    assert merged == [['632', 'mid'], ['633', 'xf1'], ['650', 'brkr'], ['671', '692'], ['684', 'tap']]


def test_an_open_switch_splits_its_bus(ieee13):
    _equipment(ieee13, 'sw_sect1').open = True
    build_topological_nodes(ieee13)
    buses = _buses(ieee13)
    assert len(buses) == 18 and ['684'] in buses and ['tap'] in buses


def test_open_falls_back_to_normal_open(ieee13):
    switch = _equipment(ieee13, 'sw_sect1')
    switch.open, switch.normalOpen = None, True
    build_topological_nodes(ieee13)
    assert len(_buses(ieee13)) == 18


def test_every_association_is_written_both_ways_and_nothing_floats(ieee13):
    cim = ieee13.cim
    build_topological_nodes(ieee13)
    for node in ieee13.graph[cim.ConnectivityNode].values():
        bus = node.TopologicalNode
        assert bus is not None and any(n is node for n in bus.ConnectivityNodes)
        for terminal in node.Terminals:
            assert terminal.TopologicalNode is bus and any(t is terminal for t in bus.Terminal)
    for bus in ieee13.graph[cim.TopologicalNode].values():
        assert any(b is bus for b in bus.ConnectivityNodeContainer.TopologicalNode)


def test_every_bus_gets_its_base_voltage(ieee13):
    cim = ieee13.cim
    build_topological_nodes(ieee13)
    volts = {bus.mRID: float(bus.BaseVoltage.nominalVoltage) for bus in ieee13.graph[cim.TopologicalNode].values()}
    assert volts['tn_sourcebus'] == 115e3 and volts['tn_650z'] == 13.2e3
    assert volts['tn_634'] == 480 and volts['tn_house'] == 240 and volts['tn_675'] == 4160


def test_conflicting_base_voltages_on_one_bus_raise(ieee13):
    cim = ieee13.cim
    [low] = [base for base in ieee13.graph[cim.BaseVoltage].values() if base.mRID == 'bv_480v']
    _equipment(ieee13, 'ln_684611').BaseVoltage = low
    with pytest.raises(ValueError, match='both'):
        build_topological_nodes(ieee13)


def test_rebuilding_replaces_the_old_topology(ieee13):
    """cim17 defect A: topology already in the model (here one-sided) was kept and nothing was rebuilt."""
    cim = ieee13.cim
    stale = cim.TopologicalNode(name='stale')
    first_terminal = next(iter(ieee13.graph[cim.Terminal].values()))
    first_terminal.TopologicalNode = stale
    ieee13.add_to_graph(stale)
    build_topological_nodes(ieee13)
    first = _buses(ieee13)
    build_topological_nodes(ieee13)
    assert _buses(ieee13) == first and len(first) == 17
    in_graph = {id(bus) for bus in ieee13.graph[cim.TopologicalNode].values()}
    assert all(id(t.TopologicalNode) in in_graph for t in ieee13.graph[cim.Terminal].values())


def test_feeder_buses_are_not_numbered(ieee13):
    build_topological_nodes(ieee13)
    assert number_buses(ieee13) == 0


# --- the node-breaker substation (test/test_models/node_breaker_substation.cimtbl) --------------

def test_node_breaker_buses(node_breaker):
    build_topological_nodes(node_breaker)
    assert _buses(node_breaker) == [['far'], ['g1'], ['j1', 'j2', 'n1'], ['n2', 't1'], ['n3', 't2']]


def test_a_retained_breaker_does_not_merge(node_breaker):
    """CB_COUPLER is closed but retained, so BB1 and BB2 stay two buses; unretained, it merges them."""
    _equipment(node_breaker, 'cb_coupler').retained = False
    build_topological_nodes(node_breaker)
    assert ['j1', 'j2', 'n1', 'n2', 't1'] in _buses(node_breaker)


def test_a_generator_behind_an_open_breaker_keeps_its_own_bus(node_breaker):
    """cim17 folded it into BB3's bus and set it out of service; here neither happens."""
    build_topological_nodes(node_breaker)
    generator = _equipment(node_breaker, 'g1m')
    assert generator.inService is None
    assert [n.mRID for n in generator.Terminals[0].TopologicalNode.ConnectivityNodes] == ['g1']
    _equipment(node_breaker, 'cb_g').open = False
    build_topological_nodes(node_breaker)
    assert ['g1', 'n3', 't2'] in _buses(node_breaker)


def test_bus_numbers(node_breaker):
    cim = node_breaker.cim
    build_topological_nodes(node_breaker)
    assert number_buses(node_breaker) == 3
    numbers = {bus.mRID: (bus.busNumber, bus.busName) for bus in node_breaker.graph[cim.TopologicalNode].values()}
    assert numbers == {'tn_n1': (100111, 'ALPHA_115_1'), 'tn_n2': (100112, 'ALPHA_115_2'),
                       'tn_t2': (100121, 'ALPHA_13_1'), 'tn_far': (None, None), 'tn_g1': (None, None)}
