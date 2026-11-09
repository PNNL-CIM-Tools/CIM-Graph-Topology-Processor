"""A cim18v17 model indexed as a LinkNet: ConnectivityNodes are nodes, Terminals are beads.

This is the reader the area and topology builders share. It is built from the Terminal side
(``Terminal.ConductingEquipment`` and ``Terminal.ConnectivityNode``, the serialized ends of both
associations), so it finds every ConductingEquipment subclass without listing classes
(``list_by_class`` matches the exact class only). A PowerTransformer or AutoTransformer is indexed
through its own Terminals; a TransformerTank has none and needs no hop.

LinkNet keys nodes and equipment by ``str(identifier)``, which is unique where names are not
(cim18v17 ConnectivityNodes and Terminals often have an mRID and no name).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from cimtopology.core.linknet import LinkNet

if TYPE_CHECKING:
    from cimgraph.models import GraphModel


def label(obj) -> str:
    """A name for messages: the name, else the mRID, else the identifier."""
    return obj.name or obj.mRID or str(obj.identifier)


@dataclass
class ModelIndex:
    """The LinkNet of a model, with arrays from each LinkNet index back to its CIM object."""

    linknet: LinkNet = field(default_factory=LinkNet)
    nodes: list = field(default_factory=lambda: [None])
    """LinkNet node -> ConnectivityNode."""
    terminals: list = field(default_factory=lambda: [None])
    """LinkNet terminal -> Terminal."""
    equipment: list = field(default_factory=lambda: [None])
    """LinkNet equipment -> ConductingEquipment."""
    _terminal_index: dict[int, int] = field(default_factory=dict, repr=False)

    def node_of(self, connectivity_node) -> int:
        return self.linknet.node[str(connectivity_node.identifier)]

    def terminal_of(self, terminal) -> int:
        return self._terminal_index[id(terminal)]

    def equipment_of(self, equipment) -> int:
        return self.linknet.equipment[str(equipment.identifier)]


def index_model(model: GraphModel) -> ModelIndex:
    """Index every ConnectivityNode and every ConductingEquipment with a Terminal."""
    cim = model.cim
    index = ModelIndex()
    for node in model.graph.get(cim.ConnectivityNode, {}).values():
        index.linknet.add_node(str(node.identifier))
        index.nodes.append(node)

    by_equipment: dict[int, tuple[object, list]] = {}
    for terminal in model.graph.get(cim.Terminal, {}).values():
        equipment = terminal.ConductingEquipment
        if equipment is None:
            raise ValueError(f"Terminal {label(terminal)} has no ConductingEquipment")
        if terminal.ConnectivityNode is None:
            raise ValueError(f"Terminal {label(terminal)} of {type(equipment).__name__} "
                             f"{label(equipment)} has no ConnectivityNode")
        by_equipment.setdefault(id(equipment), (equipment, []))[1].append(terminal)

    for equipment, terminals in by_equipment.values():
        terminals.sort(key=lambda terminal: (terminal.sequenceNumber is None, terminal.sequenceNumber or 0))
        number = index.linknet.add_equipment(
            str(equipment.identifier), [str(terminal.ConnectivityNode.identifier) for terminal in terminals])
        index.equipment.append(equipment)
        for linknet_terminal, terminal in zip(index.linknet.equipment_terminals[number], terminals, strict=True):
            index.terminals.append(terminal)
            index._terminal_index[id(terminal)] = linknet_terminal
    if len(index.nodes) != index.linknet.node_count + 1:
        raise ValueError("a Terminal names a ConnectivityNode that is not in the model graph")
    return index
