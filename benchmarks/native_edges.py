"""A native network as plain edges, read straight from a CYME ``.sxst`` file (no CIM model).

This is the pre-model view the topology processor has to work on: bus names, the sections between
them, what kind of device each section holds, and whether it is normally open. It is deliberately
crude (only what the graph operations need) and exists for the backend benchmark.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import NamedTuple

SWITCH_DEVICES = {'Switch', 'Breaker', 'Recloser', 'Sectionalizer', 'Fuse', 'NetworkProtector', 'Miscellaneous'}
TRANSFORMER_DEVICES = {'Transformer', 'TransformerByPhase', 'Regulator', 'RegulatorByPhase',
                       'ThreeWindingTransformer', 'ThreeWindingAutoTransformer', 'AutoTransformer'}


class Edge(NamedTuple):
    name: str
    bus1: str
    bus2: str
    kind: str     # 'switch', 'transformer' or 'line' (anything else that joins two buses)
    open: bool    # normally open


class Network(NamedTuple):
    nodes: list[str]      # every declared node, in file order (sections may miss some: gaps)
    edges: list[Edge]     # in file order
    sources: list[str]    # source node names


def _kind_and_state(devices) -> tuple[str, bool]:
    kind, is_open = 'line', False
    if devices is None:
        return kind, is_open
    for device in devices:
        if device.tag in TRANSFORMER_DEVICES:
            kind = 'transformer'
        elif device.tag in SWITCH_DEVICES and kind == 'line':
            kind = 'switch'
        if device.tag in SWITCH_DEVICES and device.findtext('NormalStatus') == 'Open':
            is_open = True
    return kind, is_open


def read_sxst(path: str) -> Network:
    """Stream-parse ``path`` (works on the 300 MB Duquesne file in a few seconds)."""
    nodes, edges, sources = [], [], []
    for _event, element in ET.iterparse(path, events=('end',)):
        if element.tag == 'Section':
            kind, is_open = _kind_and_state(element.find('Devices'))
            edges.append(Edge(element.findtext('SectionID'), element.findtext('FromNodeID'),
                              element.findtext('ToNodeID'), kind, is_open))
            element.clear()
        elif element.tag == 'Node':
            nodes.append(element.findtext('NodeID'))
            element.clear()
        elif element.tag == 'Source':
            sources.append(element.findtext('SourceNodeID'))
    return Network(nodes, edges, list(dict.fromkeys(sources)))
