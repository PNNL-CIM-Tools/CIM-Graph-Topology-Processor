"""Benchmark the graph backends on real native networks (CYME .sxst), before any CIM model exists.

Run (backends that are not installed are skipped):

    uv run --with networkx --with scipy --with rustworkx --with igraph python benchmarks/run.py

For each network it times build, islands (closed edges), voltage zones (non-transformer edges),
the depth-first sort-and-orient walk from the sources, and 20 single-switch updates; checks that every
backend gives the same partition and forest size; reports connectivity gaps; and, for IEEE9500, how
often the walk's bus1->bus2 orientation agrees with the hand-sorted LinesSwitchesGeometry.dss.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from backends import ALL, canonical          # noqa: E402
from native_edges import Edge, read_sxst     # noqa: E402

SXST = Path('/home/ande188/CIMHub_2_0/debug')
NETWORKS = [
    ('IEEE9500 (from DSS)', SXST / 'ieee9500_from_dss.sxst'),
    ('Beaverton', SXST / 'Beaverton_UrbanResidentialCommercial.sxst'),
    ('Secondary network (meshed)', SXST / '2023_Summer_Secondary_Network_Database.sxst'),
    ('Duquesne', SXST / 'complete_duquesne.sxst'),
]
HAND_SORTED_9500 = Path('/home/ande188/CIMHub_2_0/test_data/models/feeders/OpenDSS/PNNL/IEEE9500/'
                        'LinesSwitchesGeometry.dss')
# Known converter defects, put back so the walk can be scored. Gaps are reported before repair.
REPAIRS = {
    # DSS: New Reactor.HVMV_Sub_HSB bus1=sourcebus bus2=HVMV115_HSB1 (source impedance), dropped by DSS->SXST
    'IEEE9500 (from DSS)': [Edge('HVMV_Sub_HSB', 'sourcebus', 'hvmv115_hsb1', 'line', False)],
}
REPEATS = 3
TOGGLES = 20


def best_of(function, repeats=REPEATS):
    best, result = float('inf'), None
    for _ in range(repeats):
        start = time.perf_counter()
        result = function()
        best = min(best, time.perf_counter() - start)
    return best, result


def index(network):
    """Bus name -> index over declared nodes and every edge endpoint, plus integer edge arrays."""
    bus_index: dict[str, int] = {}
    for name in network.nodes:
        bus_index.setdefault(name, len(bus_index))
    for edge in network.edges:
        bus_index.setdefault(edge.bus1, len(bus_index))
        bus_index.setdefault(edge.bus2, len(bus_index))
    u = [bus_index[edge.bus1] for edge in network.edges]
    v = [bus_index[edge.bus2] for edge in network.edges]
    roots = [bus_index[source] for source in network.sources if source in bus_index]
    return bus_index, u, v, roots


def toggled_masks(network, closed):
    """Each of the first TOGGLES switches flipped, one at a time."""
    switches = [number for number, edge in enumerate(network.edges) if edge.kind == 'switch'][:TOGGLES]
    masks = []
    for number in switches:
        mask = list(closed)
        mask[number] = not mask[number]
        masks.append(mask)
    return masks


def gaps(network, bus_index, closed_labels, roots, u, v):
    on_edge = set(u) | set(v)
    declared = set(bus_index[name] for name in network.nodes)
    energized = {closed_labels[root] for root in roots}
    dead = [bus for bus, label in enumerate(closed_labels) if label not in energized and bus in on_edge]
    dead_islands = {closed_labels[bus] for bus in dead}
    return {
        'declared nodes on no section': len(declared - on_edge),
        'section ends not declared as nodes': len(on_edge - declared),
        'de-energized islands (closed edges, no source)': len(dead_islands),
        'buses in them': len(dead),
    }


def hand_sorted_agreement(network, bus_index, order):
    """Share of DSS lines whose hand-written bus1 is the walk's upstream bus (and, as a baseline, the
    SXST FromNodeID)."""
    pattern = re.compile(r'^New\s+Line\.(\S+)\s.*?bus1=(\S+)\s+bus2=(\S+)', re.IGNORECASE)
    hand = {}
    for line in HAND_SORTED_9500.read_text().splitlines():
        match = pattern.match(line)
        if match:
            name, bus1, _bus2 = match.groups()
            hand[name.lower()] = bus1.split('.')[0].lower()
    upstream_of = {edge: bus for edge, bus in order}
    names = {bus: name for name, bus in bus_index.items()}
    walk_agree = file_agree = total = 0
    for number, edge in enumerate(network.edges):
        bus1 = hand.get(edge.name.lower())
        if bus1 is None or number not in upstream_of:
            continue
        total += 1
        walk_agree += names[upstream_of[number]].lower() == bus1
        file_agree += edge.bus1.lower() == bus1
    return total, walk_agree, file_agree


def main():
    backends = []
    for backend in ALL:
        try:
            backend(1, [], [])
            backends.append(backend)
        except ImportError as error:
            print(f'skipping {backend.name}: {error}')

    for label, path in NETWORKS:
        start = time.perf_counter()
        network = read_sxst(str(path))
        read_seconds = time.perf_counter() - start
        bus_index, u, v, roots = index(network)
        raw_labels = ALL[1](len(bus_index), u, v).components([not edge.open for edge in network.edges])
        raw_gaps = gaps(network, bus_index, raw_labels, roots, u, v)
        if label in REPAIRS:
            network.edges.extend(REPAIRS[label])
            bus_index, u, v, roots = index(network)
        closed = [not edge.open for edge in network.edges]
        zones = [edge.kind != 'transformer' for edge in network.edges]
        masks = toggled_masks(network, closed)
        print(f'\n## {label}: {len(bus_index)} buses, {len(network.edges)} edges, {len(roots)} sources, '
              f'{sum(not ok for ok in closed)} open; read {read_seconds:.2f} s\n')
        print('| backend | build ms | islands ms | zones ms | sort+orient ms | per switch update ms |')
        print('|---|---|---|---|---|---|')

        reference = None
        for backend in backends:
            build, graph = best_of(lambda: backend(len(bus_index), u, v))
            islands_time, islands = best_of(lambda: graph.components(closed))
            zones_time, zone_labels = best_of(lambda: graph.components(zones))
            walk_time, order = best_of(lambda: graph.spanning(roots, closed))
            update_time, _ = best_of(lambda: [graph.components(mask) for mask in masks], repeats=1)
            per_update = update_time / max(len(masks), 1)
            print(f'| {backend.name} | {build*1e3:.1f} | {islands_time*1e3:.1f} | {zones_time*1e3:.1f} | '
                  f'{walk_time*1e3:.1f} | {per_update*1e3:.1f} |')

            for edge, upstream in order:
                assert upstream in (u[edge], v[edge]), f'{backend.name}: edge {edge} oriented from a non-end'
            result = (canonical(islands), canonical(zone_labels), len(order))
            if reference is None:
                reference = (backend.name, result, order)
            else:
                assert result == reference[1], f'{backend.name} disagrees with {reference[0]}'

        _, (island_labels, zone_labels, forest_edges), order = reference
        reached = forest_edges + len({island_labels[root] for root in roots})
        usable_in_reached = sum(1 for e, ok in enumerate(closed)
                                if ok and island_labels[u[e]] in {island_labels[r] for r in roots})
        print(f'\nall backends agree: {len(set(island_labels))} islands, {len(set(zone_labels))} voltage zones, '
              f'{reached} buses energized, {usable_in_reached - forest_edges} loop (non-tree) edges')
        print('connectivity gaps as read' + (f' (then repaired: {[e.name for e in REPAIRS[label]]})'
                                             if label in REPAIRS else '') + ':')
        for name, count in raw_gaps.items():
            print(f'- {name}: {count}')
        if label.startswith('IEEE9500'):
            total, walk_agree, file_agree = hand_sorted_agreement(network, bus_index, order)
            print(f'- hand-sorted DSS bus1 agrees with walk upstream: {walk_agree}/{total}; '
                  f'with SXST FromNodeID: {file_agree}/{total}')


if __name__ == '__main__':
    main()
