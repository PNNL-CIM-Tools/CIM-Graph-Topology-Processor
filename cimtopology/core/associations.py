"""Reads of CIM associations that real exports populate inconsistently.

Everything here exists because a CIM association can legitimately be serialized on
either side, and exporters disagree about which. Reading only one side works against
the file you tested with and silently finds nothing against the next one, which is the
worst failure mode available: no error, just an empty traversal.

Measured on the models this repo is developed against:

===================  ==========================  ==========================
model                ``Terminal.TopologicalNode``  ``ConnectivityNode.TopologicalNode``
===================  ==========================  ==========================
ieee13 fixture       0 of 70                     22 of 22
utility feeder       8613                        3515
transmission export  9192                        2648
===================  ==========================  ==========================

So neither side alone is safe: ieee13 populates only the ConnectivityNode side, while
transmission exports lead with the Terminal side.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Annotations only; the live profile always comes from `network.cim` at runtime.
    import cimgraph.data_profile.cimhub_2026 as cim


def node_of(terminal: cim.Terminal) -> cim.TopologicalNode | None:
    """The TopologicalNode a Terminal sits on, from whichever side carries the link.

    Prefers the direct `Terminal.TopologicalNode` and falls back to the Terminal's
    ConnectivityNode. On the ieee13 fixture the direct read is None for all 70
    terminals, so the fallback is the only path that finds anything.
    """
    if terminal.TopologicalNode is not None:
        return terminal.TopologicalNode

    connectivity_node = terminal.ConnectivityNode
    return connectivity_node.TopologicalNode if connectivity_node is not None else None
