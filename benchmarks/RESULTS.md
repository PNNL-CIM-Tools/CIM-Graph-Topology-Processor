# Graph backend benchmark (2026-11-07)

`uv run --with networkx --with scipy --with rustworkx --with igraph python benchmarks/run.py`

Inputs are native CYME `.sxst` files read as plain edges (`native_edges.py`), before any CIM model
exists: the case of sorting a malformed native file and fixing base voltages before model build.
Best of 3, milliseconds, WSL2. "islands" = components over closed edges, "zones" = components over
non-transformer edges (voltage zones), "sort+orient" = depth-first forest from the sources with
each branch oriented upstream -> downstream, "update" = islands recomputed after one switch flip.

| network | buses | edges | sources |
|---|---|---|---|
| IEEE9500 (from DSS) | 5,302 | 5,318 | 1 |
| Beaverton | 7,741 | 7,786 | 13 |
| Secondary network (meshed, 1,946 loop edges) | 21,972 | 23,948 | 267 |
| Duquesne | 128,483 | 103,764 | 122 |

Duquesne (largest):

| backend | build | islands | zones | sort+orient | per update |
|---|---|---|---|---|---|
| linknet (pure Python) | 49 | 85 | 96 | 80 | 100 |
| adjacency + union-find (pure Python) | 169 | 78 | 79 | 76 | 95 |
| networkx | 704 | 769 | 751 | 989 | 903 |
| scipy.csgraph | 4 | 9 | 9 | 238 | 10 |
| rustworkx | (lazy) | 51 | 46 | 56 | 76 |
| igraph | 17 | 20 | 21 | 300 | 21 |

Secondary network (meshed): linknet 6 / 6 / 6 / 13 / 7; networkx 104 / 134 / 116 / 139 / 123.
The rustworkx and networkx adapters rebuild the graph for each edge mask, so their operation times
include a build.

All six backends give identical island and zone partitions and forest sizes on all four networks.

## Findings beyond speed

- **IEEE9500 SXST is cut off from its source.** `sourcebus` sits on no section. The DSS
  `Reactor.HVMV_Sub_HSB` (sourcebus -> HVMV115_HSB1) was dropped by DSS->SXST, so 5,301 of 5,302
  buses are de-energized. The 11 normally-open tie switches (`SwtControl ... normal=Open`) were
  dropped too: 112 switch Lines in the DSS, 101 in the SXST. The benchmark puts the reactor back as a
  labeled repair (`REPAIRS` in run.py).
- **The hand-sorted `LinesSwitchesGeometry.dss` has 248 lines backwards.** At the bus level, IEEE9500
  is radial: its 18 "loop" edges are per-phase parallel units between the same two buses
  (CAP_1A/1B, FEEDER_REG1A/B, VREG2_A/B, ...). So orientation from the source is fixed, and 248
  of 2,629 lines have bus1 downstream, in 14 contiguous runs (the longest, file lines 90-164, is 73
  lines). The other 4 disagreements are bus names that differ between that file and the SXST.
  The sort must collapse per-phase parallel edges to one bus-level connection before it counts loops.
- **Gaps at scale:** Duquesne has 24,846 de-energized islands (51,168 buses) plus 17 declared nodes
  on no section. The secondary network has 93 (142 buses), Beaverton 32 (60 buses).

## Reading

Pure Python is about 0.1 s on a 128k-bus network, so a compiled dependency is not needed for speed.
networkx is about 10x slower than pure Python at every operation. scipy is fastest for components but
collapses parallel edges and is slow for the ordered walk.
