"""
Persistent bus number and name mapper for CIM substation topology.

Bus Number Format: (subregion_num × 100_000) + (sub_num × 100) + (volt_level_num × 10) + sequence
Bus Name Format: SUBSTATION_VOLTAGE_SEQ (max 12 characters)

PSSE bus numbers must be in range 1–999997.

Voltage levels are numbered per-substation (not globally) so volt_level_num
stays small (typically 1-5).  Sequence counts buses within a voltage level
(typically 1-9).  If sequence or volt_level_num overflow their digit slot,
a spillover counter assigns from the top of the range (999997 downward)
to guarantee uniqueness.

Example:
- Subregion "PALOUSE" (2nd alphabetically) = 2
- Substation "WENATCHEE" (5th alphabetically) = 5
- VoltageLevel "V500" (3rd at WENATCHEE alphabetically) = 3
- Sequence 1
- Result: Bus number 200531, name "WNTCH_500_1"
"""
from __future__ import annotations

import logging
import re
from typing import Dict, Tuple
from cimgraph.models import NodeBreakerModel
import cimprofiles.cim17.cim17v40 as cim

_log = logging.getLogger(__name__)


class BusNumberMapper:
    """
    Maps CIM busbars to persistent bus numbers and abbreviated names.

    Scans network once to build region/subregion mappings, then generates
    sequential bus numbers within each region/subregion/voltage group.
    Voltage levels are numbered per-substation to avoid formula overflow.
    """

    def __init__(self, network: NodeBreakerModel):
        self.network = network
        self.cim = network.cim
        self.sub_numbers: Dict[str, int] = {}
        self.subregion_numbers: Dict[str, int] = {}
        # Keyed by substation name → {volt_level_name: num}
        self.volt_level_numbers: Dict[str, Dict[str, int]] = {}
        self.next_sequence: Dict[Tuple[int, int, int], int] = {}
        self._assigned: set[int] = set()  # all bus numbers handed out
        self._spillover_next: int = 999997  # overflow range, counts down

        self._scan_network_for_regions()

    def _scan_network_for_regions(self) -> None:
        """Scan network for regions, subregions, and voltage levels.

        Voltage levels are numbered per-substation (1, 2, 3, ...) so the
        number stays small and cannot overflow into the substation digit space.
        """
        substation_names = set()
        subregion_names = set()
        # Collect voltage levels grouped by substation
        sub_to_volt_levels: Dict[str, set] = {}

        for substation in self.network.list_by_class(self.cim.Substation):
            region = substation.Region
            substation_names.add(substation.name)
            subregion_names.add(region.name)

        for volt_level in self.network.list_by_class(self.cim.VoltageLevel):
            sub_name = volt_level.Substation.name
            if sub_name not in sub_to_volt_levels:
                sub_to_volt_levels[sub_name] = set()
            sub_to_volt_levels[sub_name].add(volt_level.name)

        self.sub_numbers = {name: idx + 1 for idx, name in enumerate(sorted(substation_names))}
        self.subregion_numbers = {name: idx + 1 for idx, name in enumerate(sorted(subregion_names))}

        # Number voltage levels per-substation (1-based, sorted alphabetically)
        for sub_name, vl_names in sub_to_volt_levels.items():
            self.volt_level_numbers[sub_name] = {
                vl_name: idx + 1
                for idx, vl_name in enumerate(sorted(vl_names))
            }

        total_vl = sum(len(v) for v in self.volt_level_numbers.values())
        _log.info(
            f"Mapped {len(self.sub_numbers)} substations, "
            f"{len(self.subregion_numbers)} subregions, "
            f"{total_vl} voltage levels"
        )

    def get_bus_number_and_name(self, busbar: cim.BusbarSection) -> Tuple[int, str]:
        """Generate persistent bus number and name.

        Raises AttributeError/KeyError if required CIM data is missing.
        """
        voltage_level = busbar.EquipmentContainer
        substation = voltage_level.Substation
        voltage_kv = float(voltage_level.BaseVoltage.nominalVoltage) / 1000

        sub_num = self.sub_numbers[substation.name]
        subregion_num = self.subregion_numbers[substation.Region.name]
        volt_level_num = self.volt_level_numbers[substation.name][voltage_level.name]

        key = (subregion_num, sub_num, volt_level_num)
        sequence = self.next_sequence.get(key, 0) + 1
        self.next_sequence[key] = sequence

        bus_number = (subregion_num * 100_000) + (sub_num * 100) + (volt_level_num * 10) + sequence

        # Overflow: sequence > 9 or volt_level_num > 9 would bleed into adjacent digit slots
        if sequence > 9 or volt_level_num > 9 or bus_number > 999997 or bus_number in self._assigned:
            bus_number = self._allocate_spillover(busbar.name)
        self._assigned.add(bus_number)

        # Generate name: SUBNAME_VVV_S (max 12 chars)
        try:
            sub_name = substation.name.upper().split('STATION:')[1]
        except Exception:
            sub_name = substation.name.upper()
        clean_name = re.sub(r'[^A-Z0-9]', '', sub_name)
        voltage_str = str(int(voltage_kv))
        seq_str = str(sequence)
        max_name_length = 12 - 2 - len(voltage_str) - len(seq_str)
        clean_name = clean_name[:max(1, max_name_length)]
        bus_name = f"{clean_name}_{voltage_str}_{seq_str}"

        _log.debug(f"Busbar '{busbar.name}' → Bus {bus_number} ('{bus_name}')")

        return bus_number, bus_name

    def _allocate_spillover(self, name: str) -> int:
        """Allocate a bus number from the top of the PSSE range (999997 downward)."""
        while self._spillover_next in self._assigned:
            self._spillover_next -= 1
            if self._spillover_next < 1:
                raise RuntimeError("Exhausted all PSSE bus numbers (1–999997)")
        bus_number = self._spillover_next
        self._spillover_next -= 1
        _log.warning(f"Bus number overflow for '{name}', assigned spillover bus {bus_number}")
        return bus_number
