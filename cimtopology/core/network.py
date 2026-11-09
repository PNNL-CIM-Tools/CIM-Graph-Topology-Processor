"""The shared topology API: what a caller passes in (``Network``) and what it can ask for (``Topology``).

Every user of the topology processor (the cimhub_{tool} converters before a CIM model exists, the CIM17
and CIM18 readers after) describes its network the same way: sources, branches that keep the voltage
(lines, series elements, switches), and transformers as one coil per winding. Bus and equipment names
are the caller's own; equipment names must be unique across the network (prefix them by class, e.g.
``Line.x`` and ``Reactor.x``, where a native format allows the same name twice).

``Topology`` indexes the network once as a LinkNet (``cimtopology.core.linknet``) and answers:

- ``islands()``: buses joined through closed equipment, named by the source (or first bus) that roots them.
- ``voltage_zones()``: buses joined without crossing a transformer; an open switch keeps its voltage.
- ``sort()``: every branch and transformer exactly once, walked depth first from the sources and
  oriented upstream -> downstream (the order and bus1/bus2 of a hand-sorted file).
- ``gaps()``: what a repair step has to look at: buses on no equipment, sources on no equipment, and
  islands no source reaches.

``cimtopology.core.voltage.walk`` gives each bus its system voltage from the same ``Network``.
"""
from __future__ import annotations

from collections.abc import Hashable
from enum import Enum
from typing import NamedTuple

from cimtopology.core.linknet import NULL, LinkNet, SpanningForest, spanning_forest


class System(Enum):
    """The kind of system a bus is part of."""

    THREE_PHASE = "3-phase"
    SINGLE_PHASE = "single-phase"
    SPLIT_PHASE = "split-phase"


class Connection(Enum):
    """How a transformer coil is connected, which fixes the system voltage its kV gives."""

    POLYPHASE = "polyphase"          # kV is phase-to-phase
    PHASE_NEUTRAL = "phase-neutral"  # one single-phase coil, phase to neutral
    PHASE_PHASE = "phase-phase"      # one single-phase coil between two phase conductors
    HALF = "half"                    # one half of a split-phase secondary


class Source(NamedTuple):
    bus: str
    kv: float
    system: System


class Branch(NamedTuple):
    """Anything joining two buses that keeps the voltage: a line, a series element, a switch."""

    name: str
    bus1: str
    bus2: str
    switch: bool = False
    open: bool = False
    """Normally open. Only a switch can be open."""


class Coil(NamedTuple):
    """One transformer winding."""

    bus: str
    kv: float
    connection: Connection
    conductors: frozenset[Hashable]
    """The phase conductors it uses on its bus (any labels; the neutral left out)."""


class Transformer(NamedTuple):
    name: str
    coils: tuple[Coil, ...]


class Network(NamedTuple):
    """A network as its caller describes it, in no particular order."""

    sources: tuple[Source, ...]
    branches: tuple[Branch, ...]
    transformers: tuple[Transformer, ...]
    nodes: tuple[str, ...] = ()
    """Buses the caller knows of beyond the ends of its equipment (so a bus on nothing is a gap)."""


class SortedRow(NamedTuple):
    """One branch or transformer, in the order ``Topology.sort`` walks the network."""

    name: str
    upstream: str
    downstream: tuple[str, ...]
    """The far bus of a branch; every other bus of a transformer."""
    role: str
    """``tree`` (reaches a new bus), ``link`` (closes a loop or parallels a branch) or ``open``
    (a normally-open switch: its buses are as given, not oriented)."""
    energized: bool
    """Whether a source reaches it through closed equipment."""
    root: str
    """The source bus its walk started from, or the first bus of an island no source reaches."""


class Gaps(NamedTuple):
    isolated_nodes: tuple[str, ...]
    """Buses the caller listed that no equipment connects to."""
    isolated_sources: tuple[str, ...]
    """Source buses no equipment connects to (the source feeds nothing)."""
    unenergized: tuple[tuple[str, ...], ...]
    """Islands (through closed equipment) that no source reaches, each as its buses."""


class Topology:
    """A ``Network`` indexed as a LinkNet, with the operations of the shared API."""

    def __init__(self, network: Network):
        for branch in network.branches:
            if branch.open and not branch.switch:
                raise ValueError(f"Branch {branch.name}: only a switch can be open")
            if branch.bus1 == branch.bus2:
                raise ValueError(f"Branch {branch.name}: bus1 and bus2 are both {branch.bus1!r}")
        for transformer in network.transformers:
            if len({coil.bus for coil in transformer.coils}) < 2:
                raise ValueError(f"Transformer {transformer.name}: every coil is on one bus "
                                 f"({[coil.bus for coil in transformer.coils]})")
        self.network = network
        self.linknet = LinkNet()
        for source in network.sources:
            self.linknet.add_node(source.bus)
        for node in network.nodes:
            self.linknet.add_node(node)
        self._open: list[bool] = [False]
        self._transformer: list[bool] = [False]
        for branch in network.branches:
            self.linknet.add_equipment(branch.name, [branch.bus1, branch.bus2])
            self._open.append(branch.open)
            self._transformer.append(False)
        for transformer in network.transformers:
            self.linknet.add_equipment(transformer.name, [coil.bus for coil in transformer.coils])
            self._open.append(False)
            self._transformer.append(True)
        self._source_nodes = list(dict.fromkeys(self.linknet.node[s.bus] for s in network.sources))

    def islands(self) -> dict[str, str]:
        """Bus -> the bus that roots its island (a source where one reaches it)."""
        return self._named(self._closed_forest())

    def voltage_zones(self) -> dict[str, str]:
        """Bus -> the bus that roots its voltage zone: buses joined without crossing a transformer."""
        forest = spanning_forest(self.linknet, self._all_roots(),
                                 crosses=lambda equipment: not self._transformer[equipment])
        return self._named(forest)

    def sort(self) -> list[SortedRow]:
        """Every branch and transformer once: depth first from the sources, then the islands no
        source reaches, then the normally-open switches."""
        linknet = self.linknet
        forest = self._closed_forest(depth_first=True)
        links = set(forest.links)
        sources = set(self._source_nodes)
        rows = []
        for terminal in forest.order:
            node = linknet.terminal_node[terminal]
            root = forest.tree_of[node]
            rows.append(SortedRow(linknet.equipment_name[linknet.terminal_equipment[terminal]],
                                  linknet.node_name[node], self._downstream(terminal),
                                  'link' if terminal in links else 'tree', root in sources,
                                  linknet.node_name[root]))
        seen = set()
        for terminal in forest.boundaries:
            equipment = linknet.terminal_equipment[terminal]
            if equipment in seen:
                continue
            seen.add(equipment)
            bus1, bus2 = [linknet.terminal_node[t] for t in linknet.equipment_terminals[equipment]]
            root = forest.tree_of[bus1]
            rows.append(SortedRow(linknet.equipment_name[equipment], linknet.node_name[bus1],
                                  (linknet.node_name[bus2],), 'open', root in sources,
                                  linknet.node_name[root]))
        if len(rows) != len(linknet.equipment_name) - 1:
            raise RuntimeError(f"sort emitted {len(rows)} of {len(linknet.equipment_name) - 1} equipment")
        return rows

    def gaps(self) -> Gaps:
        linknet = self.linknet
        forest = self._closed_forest()
        sources = set(self._source_nodes)
        isolated = [node for node in range(1, linknet.node_count + 1) if linknet.last[node] == NULL]
        islands: dict[int, list[str]] = {}
        for node in forest.reached():
            root = forest.tree_of[node]
            if root not in sources and linknet.last[node] != NULL:
                islands.setdefault(root, []).append(linknet.node_name[node])
        return Gaps(isolated_nodes=tuple(linknet.node_name[n] for n in isolated if n not in sources),
                    isolated_sources=tuple(linknet.node_name[n] for n in isolated if n in sources),
                    unenergized=tuple(tuple(buses) for buses in islands.values()))

    def _all_roots(self) -> list[int]:
        return self._source_nodes + list(range(1, self.linknet.node_count + 1))

    def _closed_forest(self, depth_first: bool = False) -> SpanningForest:
        return spanning_forest(self.linknet, self._all_roots(), depth_first=depth_first,
                               crosses=lambda equipment: not self._open[equipment])

    def _named(self, forest: SpanningForest) -> dict[str, str]:
        names = self.linknet.node_name
        return {names[node]: names[forest.tree_of[node]] for node in forest.reached()}

    def _downstream(self, terminal: int) -> tuple[str, ...]:
        """The buses of ``terminal``'s equipment other than its own, in terminal order."""
        linknet = self.linknet
        own = linknet.terminal_node[terminal]
        nodes = []
        for other in linknet.equipment_terminals[linknet.terminal_equipment[terminal]]:
            node = linknet.terminal_node[other]
            if node != own and node not in nodes:
                nodes.append(node)
        return tuple(linknet.node_name[node] for node in nodes)
