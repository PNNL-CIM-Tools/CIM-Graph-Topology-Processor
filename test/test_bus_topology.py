"""TopologicalNode building on the ieee13 feeder, and the whole-topology entry point."""
import pytest

import cimgraph.data_profile.cimhub_2026 as cim

from cimtopology import build_topology
from cimtopology.distribution import build_bus_topology

from test_feeder_island import load_feeder

# ieee13 ships 22 ConnectivityNodes. Merging the zero-impedance equipment between
# them (a breaker, a recloser, two load-break switches and a fuse) leaves 17 buses,
# and merging through the three transformers as well leaves 12.
EXPECTED_CONNECTIVITY_NODES = 22
EXPECTED_NODES_XFMR_MERGED = 12
EXPECTED_NODES_XFMR_BOUNDARY = 17


@pytest.fixture
def network():
    return load_feeder()


def test_every_connectivity_node_lands_on_a_bus(network):
    """No ConnectivityNode is left without a TopologicalNode."""
    build_bus_topology(network)

    orphans = [node for node in network.list_by_class(cim.ConnectivityNode)
               if node.TopologicalNode is None]

    assert orphans == []


def test_zero_impedance_equipment_merges_buses(network):
    """Switches merge their two ends into one bus; line segments do not.

    The count is the point: bridging impedance equipment too would collapse the
    whole feeder to a single node, which is the bug this asserts against.
    """
    nodes = build_bus_topology(network, xfmr_boundary=True)

    assert len(nodes) == EXPECTED_NODES_XFMR_BOUNDARY
    assert sum(len(node.ConnectivityNodes) for node in nodes) == EXPECTED_CONNECTIVITY_NODES


def test_transformers_merge_only_when_not_a_boundary(network):
    """`xfmr_boundary` is the difference between a galvanic region and a voltage bus."""
    merged = len(build_bus_topology(network, xfmr_boundary=False))
    bounded = len(build_bus_topology(network, xfmr_boundary=True))

    assert merged == EXPECTED_NODES_XFMR_MERGED
    assert bounded == EXPECTED_NODES_XFMR_BOUNDARY
    assert merged < bounded


def test_both_association_directions_are_written(network):
    """Each side of the CN and Terminal associations points back at the other.

    Exports populate one side or the other inconsistently, so a consumer reading
    only its preferred side must still find the node.
    """
    nodes = build_bus_topology(network)

    for node in nodes:
        for connectivity_node in node.ConnectivityNodes:
            assert connectivity_node.TopologicalNode is node
        for terminal in node.Terminal:
            assert terminal.TopologicalNode is node

    for connectivity_node in network.list_by_class(cim.ConnectivityNode):
        assert connectivity_node in connectivity_node.TopologicalNode.ConnectivityNodes


def test_build_topology_materializes_nodes_and_islands(network):
    """The single entry point the consuming stack calls returns None and mutates."""
    assert build_topology(network) is None

    assert len(network.list_by_class(cim.TopologicalNode)) == EXPECTED_NODES_XFMR_MERGED
    assert len(network.list_by_class(cim.TopologicalIsland)) == 1

    for node in network.list_by_class(cim.TopologicalNode):
        assert node.TopologicalIsland is not None
        assert node in node.TopologicalIsland.TopologicalNodes


def test_build_topology_is_idempotent(network):
    """Building twice yields identical membership, not duplicated or stale objects.

    The consuming stack recomputes topology after every repair, in a loop, so a
    second call has to reproduce the first rather than accumulate.
    """
    def snapshot():
        return sorted(tuple(sorted(str(cn.mRID) for cn in node.ConnectivityNodes))
                      for node in network.list_by_class(cim.TopologicalNode))

    build_topology(network)
    first_nodes = snapshot()
    first_islands = len(network.list_by_class(cim.TopologicalIsland))

    build_topology(network)

    assert snapshot() == first_nodes
    assert len(network.list_by_class(cim.TopologicalIsland)) == first_islands


def test_rebuild_leaves_no_stale_back_references(network):
    """Every back-reference points at a node that is still in the graph."""
    build_topology(network)
    build_topology(network)

    live = {id(node) for node in network.list_by_class(cim.TopologicalNode)}

    for connectivity_node in network.list_by_class(cim.ConnectivityNode):
        assert id(connectivity_node.TopologicalNode) in live

    for terminal in network.list_by_class(cim.Terminal):
        if terminal.TopologicalNode is not None:
            assert id(terminal.TopologicalNode) in live
