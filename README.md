# CIM-Topology-Processor

A Transmission+Distribution topology processor built on the [CIM-Graph](https://github.com/PNNL-CIM-Tools/CIM-Graph) library. Processes Common Information Model (CIM) power system data to produce hierarchical distributed topology representations for grid simulation and analysis.

Designed for use with [GridAPPS-D](https://gridappsd.readthedocs.io/), dividing networks into schedulable areas:

- **Distribution Areas** — Top-level geographic regions
- **Feeder Areas** — Substation head terminal to first switch
- **Switch Areas** — Regions bounded by normally-open switches
- **Secondary Areas** — Low-voltage regions bounded by distribution transformers

## Installation

Requires Python 3.10+. Install with [uv](https://github.com/astral-sh/uv) (recommended) or pip.

```bash
# Base install
uv pip install -e .

# With GridAPPS-D integration
uv pip install -e ".[gridappsd]"

# With dev tools (Jupyter, pre-commit)
uv pip install -e ".[dev]"

# Everything
uv pip install -e ".[gridappsd,dev]"
```

Dependencies:
- `cim-graph >= 0.4.3a0`
- `gridappsd-python` (optional, for GridAPPS-D service mode)

## Usage

### As a GridAPPS-D background service

Register the service using `topology_background_service.config`, then start it:

```bash
python topology_background_service.py
```

The service listens on `goss.gridappsd.request.data.cimtopology` and responds to:

| `requestType` | Description |
|---|---|
| `GET_DISTRIBUTED_AREAS` | Returns full hierarchical topology message |
| `GET_BASE_TOPOLOGY` | Not yet supported |
| `GET_SNAPSHOT_TOPOLOGY` | Not yet supported |

Example request:

```python
import os
import json
from gridappsd import GridAPPSD

# Connect to GridAPPS-D
os.environ['GRIDAPPSD_USER'] = 'app_user'
os.environ['GRIDAPPSD_PASSWORD'] = '1234App'
gapps = GridAPPSD()
assert gapps.connected

# Request distributed topology for a feeder or distribution area by mRID
topic = "goss.gridappsd.request.data.cimtopology"
message = {
    "requestType": "GET_DISTRIBUTED_AREAS",
    "mRID": "49AD8E07-3BF9-A4E2-CB8F-C3722F837B62",  # IEEE 13-node feeder mRID
    "resultFormat": "JSON"
}
response = gapps.get_response(topic, message, timeout=30)

# Response contains the hierarchical topology message
print(json.dumps(response, indent=4))
```

The `mRID` can be a `Feeder`, `FeederArea`, or `DistributionArea` mRID — the service detects the container type automatically.

### Standalone (no GridAPPS-D)

```python
from cimgraph.databases import BlazegraphConnection
from cimtopology.utils import DistributedTopologyMessage
import cimgraph.data_profile.cimhub_2023 as cim

blazegraph = BlazegraphConnection()
container = blazegraph.get_object(mrid="<feeder-mRID>")

topo = DistributedTopologyMessage()
topo.get_context_from_feeder(container, blazegraph)

print(topo.message)
```

### Configuration

The service reads these environment variables (defaults shown):

| Variable | Default | Description |
|---|---|---|
| `CIMG_CIM_PROFILE` | `cimhub_2023` | CIM data profile |
| `CIMG_URL` | `http://localhost:8889/bigdata/namespace/kb/sparql` | Blazegraph SPARQL endpoint |
| `CIMG_NAMESPACE` | `http://iec.ch/TC57/CIM100#` | CIM namespace URI |
| `GRIDAPPSD_USER` | `app_user` | GridAPPS-D username |
| `GRIDAPPSD_PASSWORD` | `1234App` | GridAPPS-D password |

## Architecture

```
cimtopology/
├── distribution/
│   ├── distributed_topology.py   # Core graph traversal (DistributedTopology)
│   ├── feeder_area.py            # Feeder-to-first-switch areas
│   ├── switch_area.py            # Switch-bounded areas
│   ├── secondary_area.py         # Transformer secondary areas
│   └── dso_topology.py           # DSO feeder division (see Known Limitations)
├── substation/
│   ├── busbar_topology.py        # Substation bus topology
│   └── bus_number_mapper.py      # Bus numbering for simulation exports
├── transmission/
│   └── distribution_area.py      # Top-level distribution area processing
└── utils/
    ├── distributed_topo_message.py  # JSON topology message builder
    └── addressable.py               # Equipment addressability classification
```

### Topology traversal

Graph traversal follows `ConnectivityNode → Terminal → ConductingEquipment` using `DistributedTopology.expand_to_boundaries()`. Boundaries are:
- Normally-open switches (Switch, Breaker, Recloser, etc.)
- Voltage-changing transformers (secondary areas only)

### Equipment classification

**Addressable** (controllable/observable): switches, breakers, reclosers, disconnectors, load break switches, sectionalisers, power electronics (PV, battery, wind), ratio tap changers, shunt compensators, synchronous/asynchronous machines.

**Unaddressable** (passive): line segments, fuses, power transformers, transformer tanks, energy sources, energy consumers.

## Test Models

Large CIM model files are stored in `test/test_models/` and tracked with [Git LFS](https://git-lfs.github.com/). To use them after cloning:

```bash
# Install Git LFS (one-time)
git lfs install

# Pull LFS files
git lfs pull
```

Included models:
- `ieee13_distributed.xml` — IEEE 13-node test feeder with distributed area assignments
- `dso_9500_node.xml` / `.jsonld` — IEEE 9500-node model used for DSO topology development
- `ieee13_topo_msg.json` — Example topology message output for IEEE 13-node feeder

## Examples

See [`examples/9500node_example.ipynb`](examples/9500node_example.ipynb) for a worked example of loading the 9500-node model, assigning equipment containers to feeder areas, and running the topology processor.

> **Note:** The example notebook contains hardcoded paths and node names specific to the 9500-node model. See Known Limitations below.

## Known Limitations

- **`dso_topology.py` and `examples/9500node_example.ipynb` are hardcoded to the IEEE 9500-node model** for initial development. Equipment container assignment uses 9500-node naming conventions (`hvmv`, `s1`/`s2`/`s3`, etc.) and is not yet generalized.
- `get_context_from_feeder_area()` in `distributed_topo_message.py` is incomplete.
- `GET_BASE_TOPOLOGY` and `GET_SNAPSHOT_TOPOLOGY` request types are not yet implemented.

## License

See [LICENSE](LICENSE).

## Attribution and Disclaimer

This software was created under a project sponsored by the U.S. Department of Energy’s Office of Electricity, an agency of the United States Government.  Neither the United States Government nor the United States Department of Energy, nor Battelle, nor any of their employees, nor any jurisdiction or organization that has cooperated in the development of these materials, makes any warranty, express or implied, or assumes any legal liability or responsibility for the accuracy, completeness, or usefulness or any information, apparatus, product, software, or process disclosed, or represents that its use would not infringe privately owned rights.

Reference herein to any specific commercial product, process, or service by trade name, trademark, manufacturer, or otherwise does not necessarily constitute or imply its endorsement, recommendation, or favoring by the United States Government or any agency thereof, or Battelle Memorial Institute. The views and opinions of authors expressed herein do not necessarily state or reflect those of the United States Government or any agency thereof.

PACIFIC NORTHWEST NATIONAL LABORATORY
operated by
BATTELLE
for the
UNITED STATES DEPARTMENT OF ENERGY
under Contract DE-AC05-76RL01830

