"""Candidate graph backends for the topology processor, all behind one small interface.

Every backend is built from integer edge arrays (bus indices ``u[e]``, ``v[e]``) and answers:

- ``components(usable)``: component label of every bus over the edges where ``usable[e]`` is true
  (islands: closed edges; voltage zones: non-transformer edges).
- ``spanning(roots, usable)``: a depth-first spanning forest from the roots, as tree edges in
  preorder, each with its upstream bus. That is the sort-and-orient operation (bus1 upstream).

Labels are canonicalized to the smallest bus index in each component, so backends can be compared.
"""
from __future__ import annotations


def canonical(labels: list[int]) -> list[int]:
    """Relabel so each component is named by its smallest bus index."""
    smallest: dict[int, int] = {}
    for bus, label in enumerate(labels):
        smallest.setdefault(label, bus)
    return [smallest[label] for label in labels]


class LinkNet:
    """GridAPPS-D style linked lists: each bus heads a chain of terminal ids (two per edge).

    Terminal ``t`` belongs to edge ``t >> 1``; its far terminal is ``t ^ 1``.
    """
    name = 'linknet'

    def __init__(self, n_buses: int, u: list[int], v: list[int]):
        self.node_of = [0] * (2 * len(u))
        self.first = [-1] * n_buses
        self.next = [-1] * (2 * len(u))
        for edge, (bus1, bus2) in enumerate(zip(u, v)):
            for terminal, bus in ((2 * edge, bus1), (2 * edge + 1, bus2)):
                self.node_of[terminal] = bus
                self.next[terminal] = self.first[bus]
                self.first[bus] = terminal

    def components(self, usable: list[bool]) -> list[int]:
        first, nxt, node_of = self.first, self.next, self.node_of
        label = [-1] * len(first)
        for start in range(len(first)):
            if label[start] != -1:
                continue
            label[start] = start
            stack = [start]
            while stack:
                bus = stack.pop()
                terminal = first[bus]
                while terminal != -1:
                    if usable[terminal >> 1]:
                        far = node_of[terminal ^ 1]
                        if label[far] == -1:
                            label[far] = start
                            stack.append(far)
                    terminal = nxt[terminal]
        return label

    def spanning(self, roots: list[int], usable: list[bool]) -> list[tuple[int, int]]:
        first, nxt, node_of = self.first, self.next, self.node_of
        seen = [False] * len(first)
        order = []
        for root in roots:
            if seen[root]:
                continue
            seen[root] = True
            stack = [(root, first[root])]           # (bus, next terminal to try): the list *is* the iterator
            while stack:
                bus, terminal = stack[-1]
                while terminal != -1 and not (usable[terminal >> 1] and not seen[node_of[terminal ^ 1]]):
                    terminal = nxt[terminal]
                if terminal == -1:
                    stack.pop()
                    continue
                stack[-1] = (bus, nxt[terminal])
                far = node_of[terminal ^ 1]
                seen[far] = True
                order.append((terminal >> 1, bus))
                stack.append((far, first[far]))
        return order


class Adjacency:
    """Plain adjacency lists for the walk, union-find for components."""
    name = 'adjacency+unionfind'

    def __init__(self, n_buses: int, u: list[int], v: list[int]):
        self.u, self.v = u, v
        self.adjacent: list[list[tuple[int, int]]] = [[] for _ in range(n_buses)]
        for edge, (bus1, bus2) in enumerate(zip(u, v)):
            self.adjacent[bus1].append((bus2, edge))
            self.adjacent[bus2].append((bus1, edge))

    def components(self, usable: list[bool]) -> list[int]:
        parent = list(range(len(self.adjacent)))

        def root(bus: int) -> int:
            while parent[bus] != bus:
                parent[bus] = parent[parent[bus]]
                bus = parent[bus]
            return bus

        for edge, (bus1, bus2) in enumerate(zip(self.u, self.v)):
            if usable[edge]:
                parent[root(bus1)] = root(bus2)
        return [root(bus) for bus in range(len(parent))]

    def spanning(self, roots: list[int], usable: list[bool]) -> list[tuple[int, int]]:
        adjacent = self.adjacent
        seen = [False] * len(adjacent)
        order = []
        for root in roots:
            if seen[root]:
                continue
            seen[root] = True
            stack = [(root, 0)]
            while stack:
                bus, index = stack[-1]
                neighbors = adjacent[bus]
                while index < len(neighbors) and not (usable[neighbors[index][1]] and not seen[neighbors[index][0]]):
                    index += 1
                if index == len(neighbors):
                    stack.pop()
                    continue
                stack[-1] = (bus, index + 1)
                far, edge = neighbors[index]
                seen[far] = True
                order.append((edge, bus))
                stack.append((far, 0))
        return order


class NetworkX:
    name = 'networkx'

    def __init__(self, n_buses: int, u: list[int], v: list[int]):
        import networkx
        self.nx = networkx
        self.n, self.u, self.v = n_buses, u, v
        self.graph = self._graph([True] * len(u))

    def _graph(self, usable: list[bool]):
        graph = self.nx.MultiGraph()
        graph.add_nodes_from(range(self.n))
        graph.add_edges_from((bus1, bus2, edge) for edge, (bus1, bus2) in enumerate(zip(self.u, self.v))
                             if usable[edge])
        return graph

    def components(self, usable: list[bool]) -> list[int]:
        label = [0] * self.n
        for number, members in enumerate(self.nx.connected_components(self._graph(usable))):
            for bus in members:
                label[bus] = number
        return label

    def spanning(self, roots: list[int], usable: list[bool]) -> list[tuple[int, int]]:
        graph = self._graph(usable)
        seen, order = set(), []
        for root in roots:
            if root in seen:
                continue
            seen.add(root)
            for bus1, bus2 in self.nx.dfs_edges(graph, root):
                seen.add(bus2)
                order.append((next(iter(graph[bus1][bus2])), bus1))   # parallel edges: first key
        return order


class SciPy:
    name = 'scipy.csgraph'

    def __init__(self, n_buses: int, u: list[int], v: list[int]):
        import numpy
        from scipy.sparse import csgraph, csr_matrix
        self.np, self.csgraph, self.csr_matrix = numpy, csgraph, csr_matrix
        self.n = n_buses
        self.u, self.v = numpy.asarray(u), numpy.asarray(v)

    def _matrix(self, usable: list[bool]):
        mask = self.np.asarray(usable)
        u, v = self.u[mask], self.v[mask]
        ones = self.np.ones(len(u), dtype=self.np.int8)
        return self.csr_matrix((ones, (u, v)), shape=(self.n, self.n)), u, v, self.np.flatnonzero(mask)

    def components(self, usable: list[bool]) -> list[int]:
        matrix, *_ = self._matrix(usable)
        _count, labels = self.csgraph.connected_components(matrix, directed=False)
        return labels.tolist()

    def spanning(self, roots: list[int], usable: list[bool]) -> list[tuple[int, int]]:
        matrix, u, v, edges = self._matrix(usable)
        edge_of = {}
        for bus1, bus2, edge in zip(u.tolist(), v.tolist(), edges.tolist()):
            edge_of.setdefault((min(bus1, bus2), max(bus1, bus2)), edge)
        seen = self.np.zeros(self.n, dtype=bool)
        order = []
        for root in roots:
            if seen[root]:
                continue
            nodes, predecessors = self.csgraph.depth_first_order(matrix, root, directed=False,
                                                                 return_predecessors=True)
            seen[nodes] = True
            for bus in nodes[1:].tolist():
                upstream = int(predecessors[bus])
                order.append((edge_of[(min(bus, upstream), max(bus, upstream))], upstream))
        return order


class RustworkX:
    name = 'rustworkx'

    def __init__(self, n_buses: int, u: list[int], v: list[int]):
        import rustworkx
        self.rx = rustworkx
        self.n, self.u, self.v = n_buses, u, v

    def _graph(self, usable: list[bool]):
        graph = self.rx.PyGraph(multigraph=True)
        graph.add_nodes_from(range(self.n))
        graph.add_edges_from([(bus1, bus2, edge) for edge, (bus1, bus2) in enumerate(zip(self.u, self.v))
                              if usable[edge]])
        return graph

    def components(self, usable: list[bool]) -> list[int]:
        label = [0] * self.n
        for number, members in enumerate(self.rx.connected_components(self._graph(usable))):
            for bus in members:
                label[bus] = number
        return label

    def spanning(self, roots: list[int], usable: list[bool]) -> list[tuple[int, int]]:
        graph = self._graph(usable)
        seen, order = set(), []
        for root in roots:
            if root in seen:
                continue
            seen.add(root)
            for bus1, bus2 in self.rx.dfs_edges(graph, root):
                seen.add(bus2)
                order.append((graph.get_all_edge_data(bus1, bus2)[0], bus1))
        return order


class IGraph:
    name = 'igraph'

    def __init__(self, n_buses: int, u: list[int], v: list[int]):
        import igraph
        self.graph = igraph.Graph(n=n_buses, edges=list(zip(u, v)))
        self.n, self.u, self.v = n_buses, u, v

    def _subgraph(self, usable: list[bool]):
        return self.graph.subgraph_edges([edge for edge, ok in enumerate(usable) if ok], delete_vertices=False)

    def components(self, usable: list[bool]) -> list[int]:
        return self._subgraph(usable).connected_components().membership

    def spanning(self, roots: list[int], usable: list[bool]) -> list[tuple[int, int]]:
        graph = self._subgraph(usable)
        kept = [edge for edge, ok in enumerate(usable) if ok]    # subgraph edge id -> original edge id
        seen = [False] * self.n
        order = []
        for root in roots:
            if seen[root]:
                continue
            nodes, parents = graph.dfs(root)      # parents[i] is the parent of nodes[i] (visit order)
            for bus in nodes:
                seen[bus] = True
            for bus, upstream in zip(nodes[1:], parents[1:]):
                order.append((kept[graph.get_eid(upstream, bus)], upstream))
        return order


class CoreLinkNet:
    """``cimtopology.core.linknet``: the processor's own structure, names and all."""
    name = 'cimtopology.core'

    def __init__(self, n_buses: int, u: list[int], v: list[int]):
        from cimtopology.core.linknet import LinkNet as Structure, spanning_forest
        self.spanning_forest = spanning_forest
        self.linknet = Structure()
        for bus in range(n_buses):
            self.linknet.add_node(str(bus))
        for edge, (bus1, bus2) in enumerate(zip(u, v)):
            self.linknet.add_equipment(str(edge), [str(bus1), str(bus2)])

    def components(self, usable: list[bool]) -> list[int]:
        forest = self.spanning_forest(self.linknet, range(1, self.linknet.node_count + 1),
                                      crosses=lambda equipment: usable[equipment - 1])
        return forest.tree_of[1:]

    def spanning(self, roots: list[int], usable: list[bool]) -> list[tuple[int, int]]:
        forest = self.spanning_forest(self.linknet, [root + 1 for root in roots], depth_first=True,
                                      crosses=lambda equipment: usable[equipment - 1])
        links = set(forest.links)
        return [(self.linknet.terminal_equipment[t] - 1, self.linknet.terminal_node[t] - 1)
                for t in forest.order if t not in links]


ALL = [CoreLinkNet, LinkNet, Adjacency, NetworkX, SciPy, RustworkX, IGraph]
