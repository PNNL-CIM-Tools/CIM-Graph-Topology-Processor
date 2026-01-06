"""
Persistent bus number and name mapper for CIM substation topology.

Bus Number Format: (subregion_num × 10000) + (sub_num × 100) + (volt_level_num × 10) + sequence
Bus Name Format: SUBSTATION_VOLTAGE_SEQ (max 12 characters)

Example:
- Subregion "Metro" (2nd alphabetically) = 2
- Substation "Finley" (5th alphabetically) = 5
- VoltageLevel "Finley_115" (3rd alphabetically) = 3
- Sequence 1
- Result: Bus number 20531, name "FINLEY_115_1"
"""
from __future__ import annotations

import logging
import re
from typing import Dict, Tuple
from cimgraph.models import NodeBreakerModel
import cimgraph.data_profile.cim18gad as cim

_log = logging.getLogger(__name__)


class BusNumberMapper:
    """
    Maps CIM busbars to persistent bus numbers and abbreviated names.

    Scans network once to build region/subregion mappings, then generates
    sequential bus numbers within each region/subregion/voltage group.
    """

    def __init__(self, network: NodeBreakerModel):
        self.network = network
        self.cim = network.cim
        self.sub_numbers: Dict[str, int] = {}
        self.subregion_numbers: Dict[str, int] = {}
        self.volt_level_numbers: Dict[str, int] = {}
        self.next_sequence: Dict[Tuple[int, int, int, float], int] = {}

        self._scan_network_for_regions()

    def _scan_network_for_regions(self) -> None:
        """Scan network for regions, subregions, and voltage levels, assign sequential numbers."""
        substation_names = set()
        subregion_names = set()
        volt_level_names = set()

        for substation in self.network.list_by_class(self.cim.Substation):
            region = substation.Region
            substation_names.add(substation.name)
            subregion_names.add(region.name)

        for volt_level in self.network.list_by_class(self.cim.VoltageLevel):
            volt_level_names.add(volt_level.name)

        self.sub_numbers = {name: idx + 1 for idx, name in enumerate(sorted(substation_names))}
        self.subregion_numbers = {name: idx + 1 for idx, name in enumerate(sorted(subregion_names))}
        self.volt_level_numbers = {name: idx + 1 for idx, name in enumerate(sorted(volt_level_names))}

        _log.info(f"Mapped {len(self.sub_numbers)} substations, {len(self.subregion_numbers)} subregions, {len(self.volt_level_numbers)} voltage levels")

    def get_bus_number_and_name(self, busbar: cim.BusbarSection) -> Tuple[int, str]:
        """Generate persistent bus number and name. Raises AttributeError/KeyError if data missing."""
        voltage_level = busbar.EquipmentContainer
        substation = voltage_level.Substation
        voltage_kv = float(voltage_level.BaseVoltage.nominalVoltage)/1000

        sub_num = self.sub_numbers[substation.name]
        subregion_num = self.subregion_numbers[substation.Region.name]
        volt_level_num = self.volt_level_numbers[voltage_level.name]

        key = (subregion_num, sub_num, volt_level_num, voltage_kv)
        sequence = self.next_sequence.get(key, 0) + 1
        self.next_sequence[key] = sequence

        bus_number = (subregion_num * 100000) + (sub_num * 100) + (10 * volt_level_num) + sequence

        # Generate name: SUBNAME_VVV_S (max 12 chars)
        try:
            sub_name = substation.name.upper().split('STATION:')[1]
        except:
            sub_name = substation.name.upper()
        clean_name = re.sub(r'[^A-Z0-9]', '', sub_name)
        voltage_str = str(int(voltage_kv))
        seq_str = str(sequence)
        max_name_length = 12 - 2 - len(voltage_str) - len(seq_str)
        clean_name = clean_name[:max(1, max_name_length)]
        bus_name = f"{clean_name}_{voltage_str}_{seq_str}"

        _log.debug(f"Busbar '{busbar.name}' → Bus {bus_number} ('{bus_name}')")

        return bus_number, bus_name
