# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CIM-Topology-Processor is a Transmission+Distribution topology processor built on the CIM-Graph library. It processes Common Information Model (CIM) power system data to create hierarchical distributed topology representations suitable for grid simulation and analysis.

The project implements topology processing for GridAPPS-D, dividing power system networks into hierarchical scheduling areas:
- **Distribution Areas**: Top-level geographic regions
- **Feeder Areas**: Regions from substation to first switch
- **Switch Areas**: Regions bounded by switches
- **Secondary Areas**: Low-voltage regions bounded by distribution transformers

## Development Commands

### Environment Setup
```bash
# Install UV (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate
uv pip install -e .

# Install with GridAPPS-D integration (optional)
uv pip install -e ".[gridappsd]"

# Install with dev dependencies
uv pip install -e ".[dev]"

# Install everything (GridAPPS-D + dev tools)
uv pip install -e ".[gridappsd,dev]"

# Alternative: Use uv sync for faster installation
uv sync --extra gridappsd --extra dev
```

### Running the Service
```bash
# Run topology background service (requires GridAPPS-D connection)
python topology_background_service.py
```

### Development Tools
```bash
# Run Jupyter notebooks for testing/debugging
jupyter notebook debug.ipynb
```

## Architecture Overview

### Core Topology Processing Flow

1. **Input**: CIM model loaded from Blazegraph triplestore (XML/JSON-LD format)
2. **Processing**: Hierarchical topology tree construction using graph traversal
3. **Output**: JSON topology messages with equipment categorization and boundaries

### Key Components

#### `topology_background_service.py`
GridAPPS-D service that listens on `goss.gridappsd.request.data.cimtopology` topic and responds to three request types:
- `GET_DISTRIBUTED_AREAS`: Returns hierarchical topology message
- `GET_BASE_TOPOLOGY`: Not yet supported
- `GET_SNAPSHOT_TOPOLOGY`: Not yet supported

#### `cimtopology/utils/distributed_topo_message.py`
Builds the hierarchical JSON topology message. Entry points:
- `get_context_from_feeder()`: Start from Feeder object
- `get_context_from_feeder_area()`: Start from FeederArea object
- `get_context_from_distribution_area()`: Start from DistributionArea object (most comprehensive)

Each level adds equipment categorization (addressable/unaddressable), measurements, and boundary terminals.

#### `cimtopology/distribution/distributed_topology.py`
Core topology traversal logic using `DistributedTopology` class:
- `expand_to_boundaries()`: Graph traversal from root terminal until boundaries reached
- `check_boundary()`: Identifies switches and voltage-changing transformers as boundaries
- `add_to_area()`: Assigns equipment to scheduling areas

Replaces original GridAPPS-D LinkNet logic with direct CIM-Graph traversal.

#### Topology Creation Functions

**`cimtopology/distribution/feeder_area.py`**
- `create_feeder_area()`: Creates top-level area from substation head terminal to first switch
- Does not treat transformers as boundaries (xfmr_boundary=False)
- Expands from both NormalHeadTerminal and EnergySource (slack bus)

**`cimtopology/distribution/switch_area.py`**
- `create_switch_areas()`: Creates areas bounded by switches
- Iterates through all switch terminals not yet assigned to an area
- Treats transformers as boundaries by default

**`cimtopology/distribution/secondary_area.py`**
- `create_secondary_areas()`: Creates low-voltage areas on transformer secondary side
- Uses boundary terminals from parent switch area to identify transformers
- Only creates areas for transformers with voltage differences (not regulators)

#### Equipment Categorization (`cimtopology/utils/addressable.py`)

**Addressable Equipment** (controllable/observable):
- Switches, Breakers, Reclosers, Disconnectors, LoadBreakSwitches, Sectionalisers
- PowerElectronicsConnection/Units (PV, Battery, Wind)
- RatioTapChangers (tap-changing transformers)
- ShuntCompensators, Machines (Synchronous/Asynchronous)

**Unaddressable Equipment** (passive):
- ACLineSegments, Fuses, PowerTransformers, TransformerTanks
- EnergySource, EnergyConsumer

### Integration with CIM-Graph

This project depends heavily on `cim-graph` library (v0.4.3a0+):
- `cimgraph.models.FeederModel`: Centralized graph model of entire feeder
- `cimgraph.models.DistributedArea`: Sub-graph model representing a scheduling area
- `cimgraph.databases.BlazegraphConnection`: Interface to CIM triplestore
- Data profiles: `cimhub_2023`, `cimhub_ufls`, `cim18gmdm.canonical`

When modifying topology logic, understand that:
- Equipment objects have `SubSchedulingArea` attribute for assignment
- Terminal objects have `BoundedSchedulingArea` attribute to mark boundaries
- Graph traversal follows `ConnectivityNode` -> `Terminal` -> `ConductingEquipment` pattern

### Multi-Profile Support

The codebase uses different CIM data profiles in different modules:
- `cimhub_2023`: Main profile used in distributed_topo_message.py and utils
- `cimhub_ufls`: Used in distributed_topology.py
- `cim18gmdm.canonical`: Used in dso_topology.py for DSO feeder division

When working across modules, be aware that CIM class availability may differ between profiles.

## Known Issues and TODOs

1. `get_context_from_feeder_area()` in distributed_topo_message.py is incomplete (line 61)
2. Hardcoded 9500-node model logic in dso_topology.py (line 14) for hvmv switches
3. Some transformer identification logic has fallback paths for older CIM profiles without TransformerTankInfo

## Configuration

The service expects these environment variables (set in topology_background_service.py):
- `CIMG_CIM_PROFILE`: CIM data profile (e.g., 'cimhub_2023')
- `CIMG_URL`: Blazegraph SPARQL endpoint (default: http://localhost:8889/bigdata/namespace/kb/sparql)
- `CIMG_NAMESPACE`: CIM namespace URI (default: http://iec.ch/TC57/CIM100#)
- `GRIDAPPSD_USER` / `GRIDAPPSD_PASSWORD`: GridAPPS-D authentication

## File Naming and Conventions

- Test data files: Large XML/JSON-LD model files in root (dso_9500_node.xml, ieee13_distributed.xml)
- Debug notebooks: Jupyter notebooks in root (debug.ipynb)
- No formal test suite exists currently
