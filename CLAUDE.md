# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

cim-topology is the topology processor shared by the CIM tool chain. Anything that involves spanning
trees or topology processing lives here, behind one API: sorting and orienting a network, islands,
voltage zones and base voltages, connectivity gaps, buses, and the distributed areas of a feeder.
Other packages, CIMHub included, take it as a dependency.

The repo is being rewritten for the CIM17 -> CIM18 change in distribution topology. It has three layers:

| Layer | Package | Status |
|---|---|---|
| Model-agnostic core | `cimtopology.core` | LinkNet structure + shared API, tested |
| CIM18 (`cim18v17` profile) | `cimtopology.cim18` | ConnectedAreas, TopologicalNodes, bus numbers, TopologicalIslands, tested |
| CIM17 reference | `cimtopology.cim17` | frozen pre-CIM18 code, kept as the behavioral reference |

The core runs **before any CIM model exists**. Native-format converters (the `cimhub_{tool}` packages
for DSS, CYME SXST, ...) parse their own files and pass the core a `Network`. The CIM readers do the
same from a FeederModel.

```python
from cimtopology.cim18 import build_connected_areas, build_topology, number_buses
build_connected_areas(feeder_model)   # feeder / switch / secondary ConnectedAreas, returns the feeder area
build_topology(model)                 # TopologicalNodes, then TopologicalIslands (feeder or substation)
number_buses(model)                   # busNumber / busName on busbar and junction buses
```

## Development Commands

```bash
uv sync --extra dev                  # cim-graph, cimprofiles, cimtables come from sibling checkouts
.venv/bin/python -m pytest test      # all tests (core, cim17, cim18; cim18 needs ../CIMTBL-Models)
uv run --with networkx --with scipy --with rustworkx --with igraph python benchmarks/run.py
python topology_background_service.py   # GridAPPS-D service (cim17 path; needs --extra gridappsd)
```

`[tool.uv.sources]` in pyproject.toml points cim-graph, cimprofiles and cimtables at
`../CIM-Graph`, `../CIM-Profiles` and `../CIM-Tables`, as editable installs.

## Architecture

### `cimtopology/core/`: the model-agnostic core

**`linknet.py`: the LinkNet structure and spanning trees.** The core algorithm comes from the two
papers in `references/`:
- Podmore 1971, *LINKNET*: node, arc and bead elements; LIST/NEXT/ARC/END; the Figure 7 network-tree
  algorithm with tree branches, link branches and TREE(node).
- Anderson & Podmore 2022, *IEEE Access*: CIM ConnectivityNodes and Terminals in the `last`/`next`/`far`
  structures (Figure 8); breadth-first spanning trees with FirstNode/LastNode (Figure 11); merging
  closed switches by splicing lists (§V.B).

Conventions, all deliberate:
- Indices start at 1 and 0 is `NULL`, as in both papers. `test/core/test_linknet.py` rebuilds the
  2022 Figure 8 network and checks every next/far entry against the printed table.
- Each new terminal goes to the head of its node's list, so a node's list runs last-parsed first.
- For a device with 3+ terminals, `far(T)` is the node of the next terminal around the device that
  sits on a different node. This reproduces the papers for 1- and 2-terminal equipment and for the
  split-phase case, and keeps all three buses of a three-winding transformer reachable.
  `spanning_forest` expands such a device in one step.
- Switches are indexed like any equipment (the 2022 paper leaves them out). Each walk decides what it
  crosses through `crosses(equipment)`. `merge()` remains for building buses (TopologicalNodes).
- `SpanningForest` holds `tree_of`, `tree` (TREE pointers), `links`, `order` (the emission order) and
  `boundaries` (the terminals where the walk stopped, needed later for `BoundedConnectedArea`).
- Three printed `last` entries in Figure 8 contradict the table's own next/far columns. They are listed
  in `FIGURE_8_LAST_ERRATA` in the test.

**`network.py`: the shared API contract.** Callers build a
`Network(sources, branches, transformers, nodes)` from `Source`, `Branch` (name, bus1, bus2, switch,
open) and `Transformer` (one `Coil` per winding). Equipment names must be unique across the network, so
prefix them by class where a format allows duplicates. `Topology(network)` indexes it once and offers:
- `islands()`: buses joined through closed equipment, keyed to their root bus.
- `voltage_zones()`: buses joined without crossing a transformer. An open switch keeps its voltage.
- `sort()`: every branch and transformer exactly once, as `SortedRow`s. The order is depth first from
  the sources, oriented upstream -> downstream, then islands no source reaches, then normally-open
  switches (left as given). It raises an error if it would drop equipment.
- `gaps()`: isolated nodes, isolated sources and unenergized islands, as input for CIM-Repair.

Construction fails fast on an open non-switch, a branch with the same bus at both ends, a transformer
with all coils on one bus, and duplicate names.

**`voltage.py`: `walk(network)`.** Gives each bus a `BusSystem` (kV plus 3-phase, single-phase or
split-phase), and with it a BaseVoltage mRID. Ported unchanged from `cimhub_core/topology.py`, with
its union-find islands replaced by `Topology.voltage_zones()`. Its tests were ported too. This is
meant to replace `cimhub_core/connectivity/base_voltage.py`, running before the model is built.

**`dump.py`:** `write_sorted_csv` (the `sort()` rows) and `write_linknet_csv` (node and terminal
tables in the 2022 Figure 8 layout).

### `cimtopology/cim18/`: cim18v17 topology on the LinkNet core

Every builder works in place, deletes what a previous run built first (so it is safe to rerun after
switching), and writes both sides of every association. cim-graph sets neither side for you.

- `index.py`: `index_model(model)` turns the model into a `LinkNet`, with ConnectivityNodes as nodes and
  Terminals as beads. Arrays map each LinkNet index back to its CIM object. It is built from the Terminal
  side, so it finds every ConductingEquipment subclass. A Terminal without a ConnectivityNode raises.
- `boundaries.py`: `bounds_switch_area` and `changes_voltage`, the cim18 `check_boundary`. **`changes_voltage`
  is the secondary-area definition**, and the do-not-simplify rule below applies to it too.
- `areas.py`: the `ConnectedArea` writers and `trace()`, a `spanning_forest` that stops at `Cuts`.
  `feeder_area.py`, `switch_area.py`, `secondary_area.py` and the orchestrator
  `connected_areas.build_connected_areas` sit on it.
- `switching.py`: `is_open` (`open`, else `normalOpen`, else closed), `is_bus_tie` (closed and not
  `retained`), `in_service` and `energizes`.
- `topological_node.py`: buses. CNs merge across bus ties only (IEC 61970-301). An open or retained
  switch splits a bus, and lines and transformers never merge. BaseVoltage comes from the CN, its
  VoltageLevel, or the equipment (a transformer terminal's end). Conflicting values raise.
- `bus_numbers.py`: a port of cim17 `BusNumberMapper` (same formula and spillover). It writes the native
  `busNumber`/`busName` on buses holding a BusbarSection or Junction.
- `topological_island.py`: an island crosses every in-service closed piece of equipment, and bus ties
  always. The angle reference is an EnergySource bus, else a SynchronousMachine bus. Islands with
  neither are logged; they are the unenergized islands.
- `topology.py`: `build_topology(model)` builds the nodes, then the islands.

**Changes from cim17** (each is tested in `test/cim18/`):
1. Every Switch subclass except Jumper bounds a switch area, and `Switch.areaBoundary` overrides that.
   cim17 crossed Fuse and Disconnector. IEEE13 gets 5 switch areas (cim17: 4), as tier2 does.
2. `changes_voltage` reads the end BaseVoltage first, then `ratedU`, then the TankConfiguration windings.
   With none of them it raises, where cim17 took the transformer for a regulator (None == None).
3. Membership is multi-valued (`AdditionalEquipmentContainer`), and `EquipmentContainer` is never changed.
   A voltage-changing transformer belongs to its secondary area(s).
4. Secondary areas no longer overwrite their switch area's boundaries.
5. There is no DistributionArea and no `Feeder.FeederArea` (gone in cim18v17). The feeder area is the top.
6. Switch areas are numbered breadth first from the head (`{feeder mRID}.{n}`).
7. Buses follow the IEC rule, clear stale topology first (cim17 defect A), and write
   `ConnectivityNode.TopologicalNode` (cim17 defect B). There is no BusNameMarker or aliasName.
   **The isolated-shunt fold is not ported**: a shunt behind an open breaker keeps its own bus and a
   dead island, and `inService` is never changed. The fold is a PSS/E-export convention.
8. `build_topology` has no `xfmr_boundary`. A bus never spans a transformer, and an island always crosses one.

### `cimtopology/cim17/`: frozen reference

The pre-CIM18 code for `cimhub_2023` / `cim17v40`, moved from `*/archive/`:
- `distribution/`: `feeder_area`, `switch_area`, `secondary_area`, `distributed_topology`
  (`check_boundary`, `expand_to_boundaries`), `upstream_phase_tracer`, `dso_topology`.
- `substation/`: `busbar_topology`, `island_topology`, `bus_number_mapper`.
- `utils/`: `addressable`, `distributed_topo_message`. These are used by `topology_background_service.py`.

It is unchanged except for import paths and two cim-graph 0.6 compatibility fixes in `check_boundary`:
`float()` on `CIMUnit` voltages, and `getattr` for `TransformerTank.Assets`.
`test/cim17/test_distribution_areas.py` strips the areas shipped in `test/test_models/ieee13_distributed.xml`,
rebuilds them with this code, and asserts an exact match: 1 FeederArea, 4 SwitchAreas, 2 SecondaryAreas,
the same members, the same 13 boundary terminals.

**Do not refactor or "simplify" cim17.** A previous rewrite deleted the transformer-end voltage ladder in
`check_boundary` as "unnecessary". That ladder *is* the definition of a secondary area, and the branch
had to be thrown away. Any intended behavior change in the CIM18 port must be named and tested.

## CIM18 (`cim18v17`) Modeling Facts

The profile lives in the separate `cimprofiles` package (`cimprofiles.cim18.cim18v17`) and is selected
with `CIMG_CIM_PROFILE=cim18v17`. cimhub_2026 is being deleted, so don't target it.

- **Areas:** one `ConnectedArea(EquipmentContainer)` with `kind: ConnectedAreaKind` (transmission,
  subtransmission, distribution, feeder, switch, secondary, microgrid, plant, other), nested through
  `ContainedWithin`/`ContainedArea`. The CIM17 `FeederArea`/`SwitchArea`/`SecondaryArea`/`DistributionArea`
  classes are gone.
- **Membership:** `Equipment.AdditionalEquipmentContainer` <-> `EquipmentContainer.AdditionalGroupedEquipment`.
  Never overwrite `EquipmentContainer`, which holds the Feeder.
- **Boundaries:** `Terminal.BoundedConnectedArea` <-> `ConnectedArea.BoundaryTerminal`.
- **`TopologicalArea`:** kind radial/loop/meshed, under `TopologicalIsland`.
  `AreaConfiguration(priority)` links ConnectedArea and TopologicalArea.
  `Switch.topologicalUsage` (acrossArea, busTie, bypass).
- **Transformers:** `TransformerTankEnd`, `TransformerTankInfo`, `TransformerEndInfo` and `ShortCircuitTest`
  carry no meaning in CIM18, so never read them. Single-phase units are expressed through
  `TransformerPhaseEnd` (phase, phaseNeutralU), `AutoTransformerEnd`, `TransformerWinding` (ratedU,
  From/ToTransformerEnd) and `TransformerLug`. `AutoTransformer` is its own ConductingEquipment and is
  **not** a PowerTransformer subclass.
- **Ratings:** instance-level `PowerTransformerEnd`s may carry only `BaseVoltage`. In IEEE13_CDPSM,
  `tpoletop` has 4.16 kV / 240 V ends, with ratings only on its `TransformerTankConfiguration`. So
  comparing the ends' BaseVoltage is the primary voltage-change test.

## Conventions and Gotchas

- **Units:** CIM quantities are `CIMUnit` objects. Convert with `float()` or `.to('kV')` before
  comparing or hashing, and never multiply by 1e3 by hand (see the global UNITS rules).
- **`list_by_class` matches the exact class only**, not subclasses.
- **Buses are not islands.** A bus (TopologicalNode) merges only zero-impedance equipment; an island
  crosses every closed branch. Check a bus builder against a fixture's TopologicalNode count, not its
  island count.
- **Read both sides of an association** (Terminal and ConnectivityNode <-> TopologicalNode). Exports key
  off the ConnectivityNode side.
- **Per-phase parallel units** (CAP_1A/1B, regulator tanks) are parallel edges between the same two
  buses. They show up as link branches, not real loops.

## Test Data

- `test/test_models/ieee13_distributed.xml`: cimhub_2023 IEEE13, shipping the GridAPPS-D reference areas
  that `test/cim17` rebuilds. **Keep it**: it is the cim17 behavioral reference. The repo does not use Git
  LFS (these files were always plain blobs), so don't add LFS rules back to `.gitattributes`.
- `test/test_models/node_breaker_substation.cimtbl`: a hand-written cim18v17 node-breaker substation
  (retained coupler, line and transformer bays, a Junction, a generator behind an open breaker). Its
  header gives the expected buses, islands and bus numbers. No CIMTBL-Models fixture has a
  BusbarSection or VoltageLevel.
- CIMTBL-Models (`$CIMTBL_MODELS`, default `../CIMTBL-Models`; the cim18 tests skip without it):
  - `distribution/IEEE/IEEE13_CDPSM`: the CIM18 reference feeder (sub3 three-winding, reg1-3, xfm1,
    tpoletop). It has no NormalHeadTerminal, so the feeder area starts at the EnergySource.
  - `tiered_tso_dso/IEEE13/tier2_switch_delimited.cimtbl`: hand-built expected switch areas. The tests
    check the boundary terminals against it.
  - Load fixtures with `test/cim18/conftest.load`, never `cimtables.load_model` directly.
    `load_model` writes `CIMG_CIM_PROFILE` into the process environment, and `load` restores it so the
    cim17 tests still see `cimhub_2023`.
- `/home/ande188/CIMHub_2_0/debug/*.sxst`: native CYME networks for the benchmark (IEEE9500 from DSS,
  Beaverton, a meshed secondary network, Duquesne at 128k buses).

`benchmarks/RESULTS.md` records why the core is a pure-Python LinkNet: about 0.2 s per operation at
128k buses, 2-4x faster than networkx. It also records data defects the walk found. The IEEE9500 SXST
dropped its source reactor and its 11 normally-open ties, and 248 lines of the hand-sorted
`LinesSwitchesGeometry.dss` are written downstream-first.

## Configuration (GridAPPS-D service, cim17 path)

`topology_background_service.py` sets `CIMG_CIM_PROFILE=cimhub_2023`, `CIMG_URL` (Blazegraph SPARQL,
default `http://localhost:8889/bigdata/namespace/kb/sparql`), `CIMG_NAMESPACE=http://iec.ch/TC57/CIM100#`.
It authenticates with `GRIDAPPSD_USER` / `GRIDAPPSD_PASSWORD`. It answers `GET_DISTRIBUTED_AREAS` on
`goss.gridappsd.request.data.cimtopology`. `GET_BASE_TOPOLOGY` and `GET_SNAPSHOT_TOPOLOGY` are not
supported.

## Known Issues and TODOs

1. Downstream callers still import the pre-split paths, which no longer exist:
   - CIM-Repair `api.py` uses `from cimtopology import build_topology`. Change it to
     `from cimtopology.cim18 import build_topology` once it is on cim18v17; it is on cimhub_2026 today.
   - These use `cimtopology.substation.busbar_topology`: CIMHub_2_0 `psm_to_cim_service.py`, the
     main-project toolkits (psm-to-cim, data-mesh, psm-client), cascadia-model `build.py` and cascadia
     `psm.ipynb`. Change them to `cimtopology.cim17.substation` while they are on cim17v40 / cim18gad.
   - Powergrid-Models and CIMHub_2_0 `build.ipynb` use `cimtopology.distribution`. Change them to
     `cimtopology.cim17.distribution`.
2. CIMHub still uses its own `cimhub_core/topology.py`, `connectivity/base_voltage.py` and
   `cimhub_opendss/importer/cimtbl/bus_graph.py`. They should move to `cimtopology.core`.
3. Pending removal: `cimtopology/transmission/` (empty stubs).
4. cim17 known defects, pinned in cim17 and fixed in cim18: `check_boundary` reads an unrated transformer as a
   regulator (None == None). `secondary_area.py` overwrites `switch_area_model.boundaries` inside its
   own loop. `dso_topology.py` hardcodes 9500-node `hvmv` switch logic. The `BusNumberMapper` single-digit
   voltage-level slot overflows on real substations.
5. `get_context_from_feeder_area()` in `cim17/utils/distributed_topo_message.py` is incomplete.
