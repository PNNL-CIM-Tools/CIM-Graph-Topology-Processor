"""LinkNet: the linked-list network structure at the core of the topology processor.

The structure and the tree algorithm follow two papers (both in ``references/``):

- R. Podmore, "LINKNET", The Australian Computer Journal 3(3), 1971 (Podmore 1971). A network is
  node-elements and arc-elements joined by bead-elements: LIST(node) is the first bead on a node's
  list, NEXT(bead) the next bead on the same list, ARC(bead) the arc it belongs to and END(bead) the
  node at the arc's other end. Section 4.2 / Figure 7 builds a network tree by expanding from a root
  bus, labelling each branch a *tree branch* (it reaches a new bus, recorded in TREE(node)) or a
  *link branch* (it closes a loop).
- A. A. Anderson, R. Podmore et al., "Distributed Application Architecture and LinkNet Topology
  Processor for Distribution Networks Using the Common Information Model", IEEE Access 10, 2022
  (Anderson & Podmore 2022). Nodes are ConnectivityNodes and beads are Terminals, held in three
  structures: ``last`` (= LIST), ``next`` (= NEXT) and ``far`` (= END). Section V.B merges closed
  switches by splicing node lists; Section V.C / Figure 11 builds breadth-first spanning trees
  with FirstNode/LastNode counters.

The names used here are the 2022 ones. Indices start at 1, and 0 is null, as in both papers, so a
structure can be checked entry by entry against Figure 8 of the 2022 paper.

The structure knows nothing about CIM or any native format. A caller adds equipment as a name and
the names of the nodes its terminals connect to, and keeps its own attributes keyed by equipment index.

Two choices that go beyond the papers:

- **far for three or more terminals.** The 2022 paper sets far for a split-phase transformer
  (one high-side terminal, two low-side terminals on one node). A three-winding transformer on three
  distinct nodes needs a general rule, so far(T) here is the node of the next terminal around the
  equipment (cyclically) that sits on a *different* node, or T's own node if there is none. This
  gives the papers' values for one-terminal devices (far = own node), for two-terminal branches and
  for the split-phase case, and keeps every node of a multi-terminal device reachable.
- **Switches are indexed like any other equipment.** The 2022 paper leaves switches out of the
  structure and merges closed ones. Here a traversal decides which equipment it crosses: a traversal
  that crosses no switch is the paper's unmerged structure (switch-delimited areas), and one that
  crosses closed switches reaches the same nodes as the paper's merged one. ``merge`` is still
  provided, for building buses (TopologicalNodes).
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field

NULL = 0


class LinkNet:
    """The last/next/far linked lists of a network (Podmore 1971; Anderson & Podmore 2022)."""

    def __init__(self) -> None:
        self.node: dict[str, int] = {}             # node name -> index (2022 "node" structure)
        self.node_name: list[str | None] = [None]
        self.last: list[int] = [NULL]              # node -> last terminal parsed on it (1971 LIST)
        self.next: list[int] = [NULL]              # terminal -> next terminal on the same node (1971 NEXT)
        self.far: list[int] = [NULL]               # terminal -> node at the far end of its equipment (1971 END)
        self.terminal_node: list[int] = [NULL]     # terminal -> the node it is connected to
        self.terminal_equipment: list[int] = [NULL]  # terminal -> its equipment (1971 ARC)
        self.equipment: dict[str, int] = {}        # equipment name -> index
        self.equipment_name: list[str | None] = [None]
        self.equipment_terminals: list[tuple[int, ...]] = [()]
        self._members: dict[int, list[int]] = {}   # merged node -> every node sharing its list

    @property
    def node_count(self) -> int:
        return len(self.node_name) - 1

    @property
    def terminal_count(self) -> int:
        return len(self.next) - 1

    def add_node(self, name: str) -> int:
        """The index of node ``name``, adding it (with an empty list) the first time it is seen."""
        index = self.node.get(name)
        if index is None:
            index = len(self.node_name)
            self.node[name] = index
            self.node_name.append(name)
            self.last.append(NULL)
        return index

    def add_equipment(self, name: str, nodes: Sequence[str]) -> int:
        """Index one piece of equipment with a terminal on each of ``nodes``, in order (2022 Figure 10).

        Each new terminal goes to the head of its node's list (1971 section 3.1), so a node's list
        runs from the last terminal parsed back to the first.
        """
        if name in self.equipment:
            raise ValueError(f"equipment {name!r} is already in the LinkNet")
        if not nodes:
            raise ValueError(f"equipment {name!r} has no terminals")
        equipment = len(self.equipment_name)
        self.equipment[name] = equipment
        self.equipment_name.append(name)

        node_indices = [self.add_node(node) for node in nodes]
        first_terminal = len(self.next)
        terminals = tuple(range(first_terminal, first_terminal + len(node_indices)))
        for terminal, node in zip(terminals, node_indices):
            self.next.append(self.last[node])
            self.last[node] = terminal
            self.terminal_node.append(node)
            self.terminal_equipment.append(equipment)
            self.far.append(_far_node(node_indices, terminal - first_terminal))
        self.equipment_terminals.append(terminals)
        return equipment

    def terminals(self, node: int) -> Iterator[int]:
        """The terminals on ``node``'s list, last parsed first (1971 section 2.4 scan)."""
        terminal = self.last[node]
        while terminal != NULL:
            yield terminal
            terminal = self.next[terminal]

    def members(self, node: int) -> list[int]:
        """Every node sharing ``node``'s list (just ``node`` until it is merged)."""
        return self._members.get(node, [node])

    def merge(self, first: int, second: int) -> None:
        """Splice ``second``'s list onto the end of ``first``'s, so both nodes share one list (2022 V.B).

        Every node already merged with either one gets the combined list too.
        """
        first_members = self.members(first)
        second_members = self.members(second)
        if first_members is second_members:
            return
        tail = NULL
        for terminal in self.terminals(first):
            tail = terminal
        head = self.last[first] if tail != NULL else self.last[second]
        if tail != NULL:
            self.next[tail] = self.last[second]
        members = first_members + second_members
        for node in members:
            self.last[node] = head
            self._members[node] = members


def _far_node(nodes: list[int], position: int) -> int:
    """The node of the next terminal around the equipment that is on a different node."""
    own = nodes[position]
    for step in range(1, len(nodes)):
        other = nodes[(position + step) % len(nodes)]
        if other != own:
            return other
    return own


@dataclass
class SpanningForest:
    """The result of ``spanning_forest``, as arrays indexed like the LinkNet (entry 0 unused)."""

    tree_of: list[int]
    """Node -> the root of the tree that reached it, NULL if no tree did."""
    tree: list[int]
    """Node -> the terminal (bead) on the upstream node that reached it, NULL for a root or an
    unreached node (1971 TREE(NODE))."""
    links: list[int] = field(default_factory=list)
    """Terminals of link branches (each closes a loop), on the node the scan found them from."""
    order: list[int] = field(default_factory=list)
    """Terminal of every branch crossed, in the order the walk emits it (see ``spanning_forest``).
    Its node is the upstream end."""

    def reached(self) -> list[int]:
        """Every node some tree reached."""
        return [node for node, root in enumerate(self.tree_of) if root != NULL]


def spanning_forest(linknet: LinkNet, roots: Iterable[int], *,
                    crosses: Callable[[int], bool] | None = None,
                    depth_first: bool = False) -> SpanningForest:
    """Grow a tree from each root not already reached (1971 Figure 7; 2022 Figure 11).

    From the bus being expanded, each terminal on its list is taken in turn. Its equipment is
    skipped if it was already labelled, or if ``crosses(equipment)`` is false (a boundary). If it
    reaches a bus already in a tree it is a link branch; otherwise it is a tree branch, TREE(far)
    is set to it, and the far bus joins the queue. A one-terminal device (far = its own node) is not a
    branch and is skipped. A device with three or more terminals is expanded as a whole: each of
    its nodes not yet in a tree joins with TREE set to the terminal the walk met it through.

    Breadth first, the queue is the papers' FirstNode/LastNode array. With ``depth_first`` the
    most recently found bus is expanded next, which emits each path as one run (the order a
    hand-sorted file follows). Either way ``order`` lists a tree branch when its far bus is
    expanded and a link branch when it is found.
    """
    next_terminal, terminal_equipment = linknet.next, linknet.terminal_equipment
    forest = SpanningForest(tree_of=[NULL] * len(linknet.node_name), tree=[NULL] * len(linknet.node_name))
    tree_of, tree = forest.tree_of, forest.tree
    labelled = bytearray(len(linknet.equipment_name))
    emitted = bytearray(len(linknet.equipment_name))

    def join(node: int, root: int, terminal: int) -> None:
        for member in linknet.members(node):   # merged nodes share one list: they join together
            tree_of[member] = root
        tree[node] = terminal

    for root in roots:
        if tree_of[root] != NULL:
            continue
        join(root, root, NULL)
        queue = [root]
        first_node = 0                          # breadth first: the FirstNode counter; len(queue) is LastNode
        while True:
            if depth_first:
                if not queue:
                    break
                bus = queue.pop()
            else:
                if first_node == len(queue):
                    break
                bus = queue[first_node]
                first_node += 1
            entered_by = tree[bus]
            if entered_by != NULL and not emitted[terminal_equipment[entered_by]]:
                emitted[terminal_equipment[entered_by]] = 1
                forest.order.append(entered_by)
            bus_members = linknet.members(bus)
            terminal = linknet.last[bus]
            while terminal != NULL:             # scan the bus's list (1971 section 2.4)
                equipment = terminal_equipment[terminal]
                if not labelled[equipment]:
                    far_nodes = _far_nodes(linknet, terminal, equipment, bus_members)
                    if far_nodes and (crosses is None or crosses(equipment)):
                        labelled[equipment] = 1
                        new = [node for node in far_nodes if tree_of[node] == NULL]
                        if len(new) < len(far_nodes):
                            forest.links.append(terminal)
                        if not new:
                            emitted[equipment] = 1
                            forest.order.append(terminal)
                        for node in new:
                            join(node, root, terminal)
                            queue.append(node)
                terminal = next_terminal[terminal]
    return forest


def _far_nodes(linknet: LinkNet, terminal: int, equipment: int, bus_members: list[int]) -> list[int]:
    """The nodes on the far side of ``terminal``'s equipment, leaving out the bus being expanded.

    For a two-terminal branch this is just ``far`` (the papers' traversal). A device with three or
    more terminals is expanded as a whole, so every winding's node is reached from whichever
    terminal the walk meets first. A one-terminal device has none.
    """
    terminals = linknet.equipment_terminals[equipment]
    if len(terminals) == 2:
        far = linknet.far[terminal]
        return [] if far in bus_members else [far]
    nodes = []
    for other in terminals:
        node = linknet.terminal_node[other]
        if node not in bus_members and node not in nodes:
            nodes.append(node)
    return nodes
