"""Topology processing for cim18v17 models, on the LinkNet core.

- ``build_connected_areas``: feeder, switch and secondary ConnectedAreas of a feeder.
- ``build_topological_nodes`` / ``number_buses`` / ``build_topological_islands``: buses, bus numbers
  and islands, for feeders and node-breaker substations; ``build_topology`` runs nodes then islands.
  Building the buses also gives each one an empty ``SvVoltage`` and ``SvInjection``
  (``build_state_variables``): neither class references anything but its ``TopologicalNode``, so
  neither can be created before the buses nor outlive them.

Every builder works in place and deletes what a previous run built first. Behavior changes from
``cimtopology.cim17`` are listed in each module's docstring and in CLAUDE.md.
"""
from cimtopology.cim18.bus_numbers import number_buses
from cimtopology.cim18.connected_areas import build_connected_areas
from cimtopology.cim18.topological_island import build_topological_islands
from cimtopology.cim18.topological_node import (
           build_state_variables,
           build_topological_nodes,
)
from cimtopology.cim18.topology import build_topology

__all__ = ['build_connected_areas', 'build_state_variables', 'build_topological_islands',
           'build_topological_nodes', 'build_topology', 'number_buses']
