"""Crossing tank-modelled transformers on a real distribution model.

The ieee13 fixture cannot cover this: its transformers carry PowerTransformerEnds, so
a traversal that only follows `Terminal.ConductingEquipment` still works. Real
distribution models are the opposite -- the overwhelming majority of transformers are
tank-modelled and carry no terminals at all on `.Terminals` -- and there each one
splits the feeder in two unless the traversal hops
`Terminal.TransformerEnd -> TransformerTank -> PowerTransformer`.

No model is bundled: the utility exports this was developed against are not
redistributable. Point CIMTOPO_TEST_FEEDER at a tank-modelled feeder export to run
these; they skip when it is unset or missing.
"""
import os
import re

import pytest

import cimgraph.data_profile.cimhub_2026 as cim
from cimgraph.databases import XMLFile
from cimgraph.models import FeederModel

from cimtopology import build_topology
from cimtopology.distribution import bus_topology

MODEL_ENV = 'CIMTOPO_TEST_FEEDER'

# A single feeder off one substation, so a correct traversal finds a single large
# island. A handful of genuinely disconnected nodes is expected and fine; what must not
# happen is one island per transformer.
MAX_ISLANDS = 10


def load_feeder_export(path: str) -> FeederModel:
    with open(path) as model_file:
        feeder_id = re.search(
            r'<cim:Feeder rdf:about="(?:urn:uuid:)?[#_]*([0-9A-Fa-f-]{36})"',
            model_file.read()).group(1)

    network = FeederModel(container=cim.Feeder(mRID=feeder_id),
                         connection=XMLFile(filename=path))
    network.get_all_edges(cim.Feeder)
    return network


@pytest.fixture(scope='module')
def tank_feeder() -> FeederModel:
    pytest.importorskip('cimgraph')
    path = os.environ.get(MODEL_ENV)
    if not path:
        pytest.skip(f'set {MODEL_ENV} to a tank-modelled feeder export to run this')
    try:
        return load_feeder_export(path)
    except FileNotFoundError:
        pytest.skip(f'{MODEL_ENV} points at a missing file: {path}')


def test_model_is_tank_modelled(tank_feeder):
    """Guard the premise: if this model stopped using tanks the test proves nothing."""
    transformers = tank_feeder.list_by_class(cim.PowerTransformer)
    tank_ends = tank_feeder.list_by_class(cim.TransformerTankEnd)

    assert len(transformers) > 500
    assert len(tank_ends) > 1000
    # The defining property: the terminals are on the tank ends, not the transformer.
    assert sum(len(xfmr.Terminals) for xfmr in transformers) < len(transformers)


def test_whole_feeder_is_a_handful_of_islands(tank_feeder):
    """One feeder collapses to one large island, not hundreds."""
    build_topology(tank_feeder)

    islands = tank_feeder.list_by_class(cim.TopologicalIsland)
    sizes = sorted((len(island.TopologicalNodes) for island in islands), reverse=True)

    assert len(islands) <= MAX_ISLANDS
    # The bulk of the feeder is in one island, not spread across many.
    assert sizes[0] > 0.9 * sum(sizes)


def test_every_connectivity_node_reaches_a_bus(tank_feeder):
    build_topology(tank_feeder)

    orphans = [node for node in tank_feeder.list_by_class(cim.ConnectivityNode)
               if node.TopologicalNode is None]

    assert orphans == []


def test_tank_crossing_is_what_collapses_the_islands(tank_feeder, monkeypatch):
    """Control: without the tank hop the same model shatters.

    This is the test that would have caught the original defect. It pins the *cause*
    rather than the count, so it keeps failing if someone removes the tank hop while
    the island assertion above is loosened.
    """
    build_topology(tank_feeder)
    with_crossing = len(tank_feeder.list_by_class(cim.TopologicalIsland))

    # Reduce `bridging_equipment` to the naive rule: ConductingEquipment only.
    monkeypatch.setattr(bus_topology, 'bridging_equipment',
                        lambda terminal: terminal.ConductingEquipment)
    build_topology(tank_feeder)
    without_crossing = len(tank_feeder.list_by_class(cim.TopologicalIsland))

    assert with_crossing <= MAX_ISLANDS
    assert without_crossing > 100
