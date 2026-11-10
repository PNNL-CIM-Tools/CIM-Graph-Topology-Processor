"""CSV dumps: the sorted network, and the LinkNet tables in the layout of the 2022 paper's Figure 8."""
from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path

from cimtopology.core.linknet import LinkNet
from cimtopology.core.network import SortedRow

SORTED_COLUMNS = ['order', 'name', 'upstream', 'downstream', 'role', 'energized', 'root']


def write_sorted_csv(rows: Iterable[SortedRow], path: str | Path) -> None:
    """One row per branch or transformer, in ``Topology.sort`` order.

    ``upstream`` is the bus a hand-sorted file writes as bus1; ``downstream`` lists the other buses
    (one for a branch, separated by spaces for a transformer with more windings).
    """
    with open(path, 'w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(SORTED_COLUMNS)
        for order, row in enumerate(rows, start=1):
            writer.writerow([order, row.name, row.upstream, ' '.join(row.downstream), row.role,
                             str(row.energized).lower(), row.root])


def write_linknet_csv(linknet: LinkNet, nodes_path: str | Path, terminals_path: str | Path) -> None:
    """The LinkNet structure as two tables, indexed as in Figure 8 of Anderson & Podmore (2022).

    nodes: ``node, name, last``. terminals: ``term, next, far, node, equipment``
    (``node`` is the terminal's own node; ``equipment`` names the device it belongs to).
    """
    with open(nodes_path, 'w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['node', 'name', 'last'])
        for node in range(1, linknet.node_count + 1):
            writer.writerow([node, linknet.node_name[node], linknet.last[node]])
    with open(terminals_path, 'w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['term', 'next', 'far', 'node', 'equipment'])
        for terminal in range(1, linknet.terminal_count + 1):
            writer.writerow([terminal, linknet.next[terminal], linknet.far[terminal],
                             linknet.terminal_node[terminal],
                             linknet.equipment_name[linknet.terminal_equipment[terminal]]])
