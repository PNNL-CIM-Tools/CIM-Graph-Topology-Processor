"""Islands on the ieee13 feeder, checked against the fixture's own island."""
import re

import pytest

import cimgraph.data_profile.cimhub_2026 as cim
from cimgraph.databases import XMLFile
from cimgraph.models import FeederModel

from cimtopology.distribution import build_feeder_islands
from cimtopology.distribution.bus_topology import equipment_terminals
from cimtopology.distribution.feeder_island import _conducting_branches

MODEL = 'test/test_models/ieee13_distributed.xml'

# The fixture ships one island over all 22 nodes, angle reference 'sourcebus'.
EXPECTED_NODES = 22
EXPECTED_ANGLE_REF = 'sourcebus'


def load_feeder() -> FeederModel:
    """A fresh FeederModel per test, so switch changes never leak between them."""
    with open(MODEL) as model_file:
        feeder_id = re.search(r'<cim:Feeder rdf:about="urn:uuid:([^"]+)"',
                              model_file.read()).group(1)

    network = FeederModel(container=cim.Feeder(mRID=feeder_id),
                          connection=XMLFile(filename=MODEL))
    network.get_all_edges(cim.Feeder)
    return network


@pytest.fixture
def network() -> FeederModel:
    return load_feeder()


def test_closed_feeder_is_one_island(network):
    """Every switch closed, so the whole feeder is a single energized island."""
    islands = build_feeder_islands(network)

    assert len(islands) == 1
    assert len(islands[0].TopologicalNodes) == EXPECTED_NODES
    assert islands[0].AngleRefTopologicalNode.name == EXPECTED_ANGLE_REF


def test_every_node_lands_in_an_island(network):
    """No TopologicalNode is left without an island."""
    build_feeder_islands(network)

    orphans = [node.name for node in network.list_by_class(cim.TopologicalNode)
               if node.TopologicalIsland is None]

    assert orphans == []


def test_open_switch_splits_the_feeder(network):
    """Opening the recloser separates the feeder into two islands."""
    recloser = network.list_by_class(cim.Recloser)[0]
    recloser.open = True

    islands = build_feeder_islands(network)

    assert len(islands) == 2
    assert sum(len(island.TopologicalNodes) for island in islands) == EXPECTED_NODES

    # The source keeps the angle reference; the cut-off side has no generation
    # of its own, so it correctly reports none rather than an arbitrary node.
    largest, smallest = islands
    assert largest.AngleRefTopologicalNode.name == EXPECTED_ANGLE_REF
    assert smallest.AngleRefTopologicalNode is None


def test_rebuild_replaces_islands(network):
    """Rebuilding after reclosing returns to one island, with no leftovers."""
    recloser = network.list_by_class(cim.Recloser)[0]
    recloser.open = True
    build_feeder_islands(network)

    recloser.open = False
    islands = build_feeder_islands(network)

    assert len(islands) == 1
    assert len(network.list_by_class(cim.TopologicalIsland)) == 1
    assert len(islands[0].TopologicalNodes) == EXPECTED_NODES


def test_islands_are_sorted_largest_first(network):
    """Callers rely on islands[0] being the main energized island."""
    fuse = network.list_by_class(cim.Fuse)[0]
    fuse.open = True

    islands = build_feeder_islands(network)
    sizes = [len(island.TopologicalNodes) for island in islands]

    assert sizes == sorted(sizes, reverse=True)


def test_branch_equipment_is_not_limited_to_a_class_list(network):
    """Any multi-terminal equipment carries an island, including classes no list names.

    Branch equipment is found by counting terminals, not by matching against a list of
    concrete classes. `EarthingSwitch` is the regression guard: it is a Switch subclass
    that an enumerated list plausibly omits (the earlier one did), and omitting it drops
    a real island edge silently. Splicing one between two nodes must make it visible.
    """
    first, second = network.list_by_class(cim.ConnectivityNode)[:2]

    earthing_switch = cim.EarthingSwitch()
    earthing_switch.uuid(name='test-earthing-switch')
    earthing_switch.open = False
    for connectivity_node in (first, second):
        terminal = cim.Terminal()
        terminal.uuid(name=f'test-earthing-terminal-{connectivity_node.name}')
        terminal.ConductingEquipment = earthing_switch
        terminal.ConnectivityNode = connectivity_node
        earthing_switch.Terminals.append(terminal)
        connectivity_node.Terminals.append(terminal)
        network.add_to_graph(terminal)
    network.add_to_graph(earthing_switch)

    branches = _conducting_branches(network)

    assert earthing_switch in branches


def test_single_terminal_equipment_is_not_a_branch(network):
    """Loads and sources span nothing, so they cannot carry an island."""
    branches = _conducting_branches(network)

    assert all(len(equipment_terminals(equipment)) > 1 for equipment in branches)
    assert not any(isinstance(equipment, (cim.EnergyConsumer, cim.EnergySource))
                   for equipment in branches)


def _attach(network, connectivity_node, equipment, name):
    """Hang a new piece of equipment on an existing ConnectivityNode."""
    equipment.uuid(name=name)
    terminal = cim.Terminal()
    terminal.uuid(name=f'{name}-terminal')
    terminal.ConductingEquipment = equipment
    terminal.ConnectivityNode = connectivity_node
    equipment.Terminals.append(terminal)
    connectivity_node.Terminals.append(terminal)
    network.add_to_graph(terminal)
    network.add_to_graph(equipment)
    return equipment


def _de_energized_island(network):
    """Open the recloser and return the island left with no angle reference."""
    network.list_by_class(cim.Recloser)[0].open = True
    islands = build_feeder_islands(network)
    dead = [island for island in islands if island.AngleRefTopologicalNode is None]
    assert dead, 'expected the cut-off side to have no angle reference'
    return dead[0]


def test_induction_machine_is_not_an_angle_reference(network):
    """An AsynchronousMachine follows the grid's angle; it cannot establish one.

    It is a `RotatingMachine` alongside SynchronousMachine, so a reference test written
    against the base class wrongly treats an induction motor as generation and reports a
    dead island as energized. This is the regression guard for that.
    """
    dead = _de_energized_island(network)
    connectivity_node = dead.TopologicalNodes[0].ConnectivityNodes[0]

    _attach(network, connectivity_node, cim.AsynchronousMachine(), 'induction-motor')
    islands = build_feeder_islands(network)

    still_dead = [island for island in islands
                  if island.AngleRefTopologicalNode is None]
    assert still_dead, 'an induction machine must not become an angle reference'


def test_synchronous_machine_energizes_a_cut_off_island(network):
    """Local synchronous generation can hold up an island cut off from the source."""
    dead = _de_energized_island(network)
    node = dead.TopologicalNodes[0]

    _attach(network, node.ConnectivityNodes[0], cim.SynchronousMachine(), 'local-genset')
    islands = build_feeder_islands(network)

    island = next(candidate for candidate in islands
                  if any(member.identifier == node.identifier
                         for member in candidate.TopologicalNodes))
    assert island.AngleRefTopologicalNode is not None


def test_grid_following_inverter_is_not_an_angle_reference(network):
    """A PowerElectronicsConnection counts only when `isGridForming` is True.

    The attribute is optional and unset in every model seen so far, and unset means
    "not stated" -- so an ordinary grid-following PV inverter must not be mistaken for
    something that can energize an island.
    """
    dead = _de_energized_island(network)
    connectivity_node = dead.TopologicalNodes[0].ConnectivityNodes[0]
    inverter = _attach(network, connectivity_node,
                       cim.PowerElectronicsConnection(), 'pv-inverter')

    assert inverter.isGridForming is None
    assert [island for island in build_feeder_islands(network)
            if island.AngleRefTopologicalNode is None]

    inverter.isGridForming = True
    islands = build_feeder_islands(network)

    assert not [island for island in islands
                if island.AngleRefTopologicalNode is None]
