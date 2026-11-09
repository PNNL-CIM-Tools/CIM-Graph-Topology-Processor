"""Writing cim18v17 ConnectedAreas, and the one trace every area kind is built from.

cim18v17 has one ``ConnectedArea`` class with a ``kind`` where cim17 had FeederArea, SwitchArea and
SecondaryArea. The associations it uses (cim-graph sets neither side for you, so both are written):

- nesting: ``ConnectedArea.ContainedWithin`` <-> ``ContainedArea``;
- membership: ``Equipment.AdditionalEquipmentContainer`` <-> ``AdditionalGroupedEquipment``. Membership
  never touches ``Equipment.EquipmentContainer``, which holds the Feeder or Substation;
- boundaries: ``Terminal.BoundedConnectedArea`` <-> ``ConnectedArea.BoundaryTerminal``. A terminal
  bounds the area on its own side of the boundary equipment.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cimtopology.cim18.boundaries import bounds_switch_area, changes_voltage, is_transformer
from cimtopology.cim18.index import ModelIndex, label
from cimtopology.core.linknet import spanning_forest

if TYPE_CHECKING:
    from cimgraph.models import GraphModel

BUILT_KINDS = ('feederArea', 'switchArea', 'secondaryArea')
"""The ConnectedArea kinds this package builds, and so clears before a rebuild."""


@dataclass
class Cuts:
    """Equipment index -> whether it bounds an area, worked out once per build."""

    switch: list[bool]
    """Bounds a switch area (``bounds_switch_area``)."""
    step: list[bool]
    """A transformer that changes voltage (``changes_voltage``)."""
    zone: list[bool]
    """Either of the above: what bounds a switch or secondary area."""


def find_cuts(index: ModelIndex, cim) -> Cuts:
    """Raises (from ``changes_voltage``) if a transformer cannot be told from a regulator."""
    switch, step = [False], [False]
    for equipment in index.equipment[1:]:
        switch.append(bounds_switch_area(equipment, cim))
        step.append(is_transformer(equipment, cim) and changes_voltage(equipment, cim))
    return Cuts(switch, step, [cut or change for cut, change in zip(switch, step, strict=True)])


@dataclass
class Trace:
    """What one area holds, as CIM objects."""

    nodes: list
    """ConnectivityNodes the trace reached."""
    equipment: list
    """Equipment with a terminal on a reached node, except the equipment the trace stopped at."""
    boundaries: list
    """Terminals the trace stopped at: on a reached node, of equipment it did not cross."""


def trace(index: ModelIndex, roots: Iterable[int], *, stops_at: list[bool]) -> Trace:
    """Everything reachable from the ``roots`` nodes without crossing equipment ``stops_at`` marks."""
    linknet = index.linknet
    forest = spanning_forest(linknet, roots, crosses=lambda equipment: not stops_at[equipment])
    reached = forest.reached()
    stopped = {linknet.terminal_equipment[terminal] for terminal in forest.boundaries}
    members: list[int] = []
    seen: set[int] = set()
    for node in reached:
        for terminal in linknet.terminals(node):
            equipment = linknet.terminal_equipment[terminal]
            if equipment not in stopped and equipment not in seen:
                seen.add(equipment)
                members.append(equipment)
    return Trace(nodes=[index.nodes[node] for node in reached],
                 equipment=[index.equipment[equipment] for equipment in members],
                 boundaries=[index.terminals[terminal] for terminal in forest.boundaries])


def create_area(model: GraphModel, kind: str, name: str, parent=None):
    """A ConnectedArea of ``kind`` (a ConnectedAreaKind name), contained within ``parent``."""
    cim = model.cim
    area = cim.ConnectedArea(name=name, kind=cim.ConnectedAreaKind[kind])
    area.uuid(mRID=f'area_{name}')
    if parent is not None:
        area.ContainedWithin = parent
        parent.ContainedArea.append(area)
    model.add_to_graph(area)
    return area


def add_member(equipment, area, cim) -> None:
    """Put ``equipment`` in ``area``, with the tanks of a transformer and the units of an inverter
    (they have no Terminals of their own, so no trace reaches them)."""
    items = [equipment]
    if isinstance(equipment, cim.PowerTransformer):
        items += equipment.TransformerTanks
    elif isinstance(equipment, cim.PowerElectronicsConnection):
        items += equipment.PowerElectronicsUnit
    for item in items:
        if not any(container is area for container in item.AdditionalEquipmentContainer):
            item.AdditionalEquipmentContainer.append(area)
            area.AdditionalGroupedEquipment.append(item)


def add_boundary(terminal, area) -> None:
    """Mark ``terminal`` as bounding ``area``. A terminal bounds one area only (0..1 in cim18v17)."""
    if terminal.BoundedConnectedArea is area:
        return
    if terminal.BoundedConnectedArea is not None:
        raise ValueError(f"Terminal {label(terminal)} already bounds area "
                         f"{label(terminal.BoundedConnectedArea)}; cannot also bound {label(area)}")
    terminal.BoundedConnectedArea = area
    area.BoundaryTerminal.append(terminal)


def fill_area(area, found: Trace, cim) -> None:
    """Write a trace into ``area``: its members and its boundary terminals."""
    for equipment in found.equipment:
        add_member(equipment, area, cim)
    for terminal in found.boundaries:
        add_boundary(terminal, area)


def clear_areas(model: GraphModel) -> None:
    """Delete the feeder, switch and secondary areas a previous build made (other kinds are kept).

    ``GraphModel.delete`` also removes every reference to the deleted area, from both sides.
    """
    cim = model.cim
    for area in list(model.graph.get(cim.ConnectedArea, {}).values()):
        if area.kind is not None and area.kind.name in BUILT_KINDS:
            model.delete(area)
