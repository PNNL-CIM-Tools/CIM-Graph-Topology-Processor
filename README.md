# CIM-Topology-Processor

A Transmission+Distribution topology processor built on the CIM-Graph library. This tool processes Common Information Model (CIM) power system data to create hierarchical distributed topology representations suitable for grid simulation and analysis.

## Features

- Hierarchical topology processing for transmission and distribution power systems
- Support for GridAPPS-D integration
- Creates scheduling areas at multiple levels:
  - Distribution Areas (top-level geographic regions)
  - Feeder Areas (substation to first switch)
  - Switch Areas (regions bounded by switches)
  - Secondary Areas (low-voltage regions bounded by transformers)
- Equipment categorization (addressable/unaddressable)
- Measurement and boundary terminal identification

## Installation

### From PyPI

```bash
pip install cim-topology
```

### With GridAPPS-D Support

```bash
pip install cim-topology[gridappsd]
```

### Development Installation

```bash
# Clone the repository
git clone https://github.com/PNNL-CIM-Tools/CIM-Graph-Topology-Processor.git
cd CIM-Graph-Topology-Processor

# Install with UV (recommended)
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"

# Or with pip
pip install -e ".[dev]"
```

## Usage

### As a GridAPPS-D Service

Run the topology background service that listens for topology requests:

```bash
python topology_background_service.py
```

The service responds to requests on the `goss.gridappsd.request.data.cimtopology` topic with three request types:
- `GET_DISTRIBUTED_AREAS`: Returns hierarchical topology message
- `GET_BASE_TOPOLOGY`: (Not yet implemented)
- `GET_SNAPSHOT_TOPOLOGY`: (Not yet implemented)

### As a Python Library

```python
from cimgraph.models import FeederModel
from cimgraph.databases import BlazegraphConnection
from cimtopology.utils.distributed_topo_message import get_context_from_distribution_area

# Connect to CIM data source
conn = BlazegraphConnection(url="http://localhost:8889/bigdata/namespace/kb/sparql")

# Load feeder model
feeder = FeederModel(connection=conn, container="my_feeder_mrid")

# Generate topology message
topology = get_context_from_distribution_area(feeder.graph)
```

## Requirements

- Python >= 3.10
- cim-graph >= 0.4.3a0

## Documentation

For detailed documentation on the topology processing algorithms and integration with GridAPPS-D, see [CLAUDE.md](CLAUDE.md).

## License

This project is licensed under the BSD 3-Clause License - see the [LICENSE](LICENSE) file for details.

## Copyright

Copyright (c) 2025, Battelle Memorial Institute. All rights reserved.

## Contributing

This is an alpha release. Contributions, issues, and feature requests are welcome!
