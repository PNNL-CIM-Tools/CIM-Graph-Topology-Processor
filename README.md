# CIM-Topology-Processor

![GitHub Tag](https://img.shields.io/github/v/tag/PNNL-CIM-Tools/CIM-Graph-Topology-Processor)
![GitHub Release Date](https://img.shields.io/github/release-date-pre/PNNL-CIM-Tools/CIM-Graph-Topology-Processor)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/PNNL-CIM-Tools/CIM-Graph/release.yml)
![Libraries.io dependency status for GitHub repo](https://img.shields.io/librariesio/github/PNNL-CIM-Tools/CIM-Graph-Topology-Processor)


![PyPI - Version](https://img.shields.io/pypi/v/cim-topology)
![PyPI - Downloads](https://img.shields.io/pypi/dm/cim-topology?label=pypi%20downloads)
![PyPI - Format](https://img.shields.io/pypi/format/cim-topology)


![GitHub Issues or Pull Requests](https://img.shields.io/github/issues/PNNL-CIM-Tools/CIM-Graph-Topology-Processor)
![GitHub Issues or Pull Requests](https://img.shields.io/github/issues-pr/PNNL-CIM-Tools/CIM-Graph-Topology-Processor)
![GitHub commit activity](https://img.shields.io/github/commit-activity/t/PNNL-CIM-Tools/CIM-Graph-Topology-Processor)

![GitHub Downloads (all assets, all releases)](https://img.shields.io/github/downloads/PNNL-CIM-Tools/CIM-Graph-Topology-Processor/total?label=git%20downloads)
![GitHub License](https://img.shields.io/github/license/PNNL-CIM-Tools/CIM-Graph-Topology-Processor)

The topology processor shared by the CIM tool chain (CIMHub, CIM-Repair, GridAPPS-D). Everything
that involves spanning trees or topology processing lives here behind one API: sorting and orienting a
network, islands, voltage zones and base voltages, connectivity gaps, and the distributed areas of a
feeder.

The core is a pure-Python LinkNet structure, from the two papers in [`references/`](references):

- R. Podmore, *LINKNET: a structure for computer representation and solution of electric power
  networks*, 1971.
- A. Anderson and R. Podmore, *IEEE Access*, 2022: LinkNet over CIM ConnectivityNodes and Terminals.

[`benchmarks/RESULTS.md`](benchmarks/RESULTS.md) compares it with networkx, scipy, rustworkx and
igraph on networks up to 128k buses.

## Status

The repo is being rewritten for the CIM17 -> CIM18 change in distribution topology.

| Package | Status |
|---|---|
| `cimtopology.core` | Model-agnostic LinkNet core and shared API. Tested. |
| `cimtopology.cim18` | `cim18v17` models: feeder, switch and secondary `ConnectedArea`s; `TopologicalNode`s, bus numbers and `TopologicalIsland`s for feeders and node-breaker substations. Tested. |
| `cimtopology.cim17` | Frozen pre-CIM18 code (`cimhub_2023` / `cim17v40`), kept as the behavioral reference. |

## Installation

Requires Python 3.10+ and [uv](https://github.com/astral-sh/uv).

```bash
uv sync --extra dev                 # cim-graph, cimprofiles and cimtables from sibling checkouts
uv sync --extra dev --extra gridappsd   # plus the GridAPPS-D service
.venv/bin/python -m pytest test
```

`[tool.uv.sources]` in `pyproject.toml` points `cim-graph`, `cimprofiles` and `cimtables` at
`../CIM-Graph`, `../CIM-Profiles` and `../CIM-Tables`.

## Usage

### The core: no CIM model needed

A format converter (a `cimhub_{tool}` package for DSS, CYME SXST, ...) describes its network and
asks for the topology. This runs before any CIM model exists, so every bus can get the right
BaseVoltage, and the gaps can go to CIM-Repair.

```python
from cimtopology.core import (Branch, Coil, Connection, Network, Source, System, Topology, Transformer,
                              walk, write_sorted_csv)

network = Network(
    sources=(Source('src', 12.47, System.THREE_PHASE),),
    branches=(Branch('l1', 'a', 'src'), Branch('sw1', 'a', 'b', switch=True, open=True)),
    transformers=(Transformer('xf1', (Coil('a', 12.47, Connection.POLYPHASE, frozenset({1, 2, 3})),
                                      Coil('lv', 0.48, Connection.POLYPHASE, frozenset({1, 2, 3})))),),
)
topology = Topology(network)
topology.islands()          # bus -> root bus, through closed equipment
topology.voltage_zones()    # bus -> root bus, without crossing a transformer
topology.gaps()             # isolated nodes, isolated sources, unenergized islands
write_sorted_csv(topology.sort(), 'sorted.csv')   # each branch once, oriented from the source
walk(network)['lv']         # BusSystem(0.48, THREE_PHASE); its .base_voltage is 'bv_480v'
```

### CIM18 (`cim18v17`) models

```python
import cimtables
from cimtopology.cim18 import build_connected_areas, build_topology, number_buses

feeder = cimtables.load_model('IEEE13_CDPSM.cimtbl')
feeder_area = build_connected_areas(feeder)   # ConnectedArea tree: feeder > switch > secondary
build_topology(feeder)                        # TopologicalNodes, then TopologicalIslands
number_buses(substation_model)                # busNumber / busName for busbar buses
```

Each builder works in place and can be rerun after switching. `CLAUDE.md` lists what changed from the
CIM17 code.

### GridAPPS-D background service (CIM17)

`topology_background_service.py` runs the CIM17 distributed-area code against Blazegraph. Register it
with `topology_background_service.config`, then start it:

```bash
python topology_background_service.py
```

It listens on `goss.gridappsd.request.data.cimtopology`. `GET_DISTRIBUTED_AREAS` returns the
hierarchical topology message for a `Feeder`, `FeederArea` or `DistributionArea` mRID.
`GET_BASE_TOPOLOGY` and `GET_SNAPSHOT_TOPOLOGY` are not supported.

```python
from gridappsd import GridAPPSD

gapps = GridAPPSD()
message = {"requestType": "GET_DISTRIBUTED_AREAS",
           "mRID": "49AD8E07-3BF9-A4E2-CB8F-C3722F837B62",  # IEEE 13-node feeder
           "resultFormat": "JSON"}
response = gapps.get_response("goss.gridappsd.request.data.cimtopology", message, timeout=30)
```

The service sets `CIMG_CIM_PROFILE=cimhub_2023`,
`CIMG_URL=http://localhost:8889/bigdata/namespace/kb/sparql` and
`CIMG_NAMESPACE=http://iec.ch/TC57/CIM100#`, and authenticates with `GRIDAPPSD_USER` /
`GRIDAPPSD_PASSWORD`.

## Test Models

`test/test_models/` holds plain files (no Git LFS):

- `ieee13_distributed.xml`: IEEE 13-node feeder (`cimhub_2023`) with the GridAPPS-D reference areas.
  `test/cim17` rebuilds the areas and checks them against it.
- `new_topo_message.json`: the shape of the topology message.
- `node_breaker_substation.cimtbl`: a small `cim18v17` node-breaker substation for the bus and island tests.

The CIM18 (`cim18v17`) fixtures are the `.cimtbl` files in CIMTBL-Models.

[`examples/9500node_example.ipynb`](examples/9500node_example.ipynb) is the CIM17-era DSO development
notebook for `cim17/distribution/dso_topology.py`. Like that module, it is hardcoded to IEEE 9500
names and to local paths.

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

