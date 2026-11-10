"""What bounds a ConnectedArea: area-boundary switches and voltage-changing transformers.

These two predicates replace cim17 ``check_boundary`` (``cimtopology/cim17/distribution/
distributed_topology.py``). ``changes_voltage`` is the definition of a secondary area: a transformer
that changes voltage bounds one, and a regulator (equal voltages on every winding) is crossed. Do not
simplify it away; see CLAUDE.md.

Changes from cim17, each tested in ``test/cim18/test_boundaries.py``:

- Every Switch subclass bounds a switch area except a Jumper, unless ``Switch.areaBoundary`` says
  otherwise. cim17 bounded only Breaker, Sectionaliser, Recloser, LoadBreakSwitch and Switch, and
  crossed Fuse and Disconnector.
- The voltage test reads the ends' BaseVoltage first. cim18v17 instance ends may carry only a
  BaseVoltage (IEEE13_CDPSM tpoletop), with the ratings on the TransformerTankConfiguration.
- A transformer with no voltages to compare raises. cim17 read missing ratings as equal (None == None)
  and so took an unrated transformer for a regulator.
- TransformerTankEnd, TransformerTankInfo, TransformerEndInfo and ShortCircuitTest carry no meaning
  in CIM18 and are never read.
"""
from __future__ import annotations

import math

from cimtopology.cim18.index import label


def bounds_switch_area(equipment, cim) -> bool:
    """A switch that cuts the feeder into switch areas."""
    if not isinstance(equipment, cim.Switch):
        return False
    if equipment.areaBoundary is not None:
        return bool(equipment.areaBoundary)
    return not isinstance(equipment, cim.Jumper)


def is_transformer(equipment, cim) -> bool:
    """A PowerTransformer, or an AutoTransformer (which is not a PowerTransformer subclass)."""
    return isinstance(equipment, (cim.PowerTransformer, cim.AutoTransformer))


def changes_voltage(transformer, cim) -> bool:
    """Whether the windings of ``transformer`` are at different voltages (a regulator's are not).

    The first source that gives a voltage for every winding decides:

    1. the BaseVoltage of every end (PowerTransformerEnd or AutoTransformerEnd);
    2. the end ratings: PowerTransformerEnd.ratedU, or AutoTransformerEnd.baseU;
    3. the ratings of the tanks' windings (TransformerTankConfiguration.TransformerWinding.ratedU),
       for a PowerTransformer whose ends carry neither.

    Raises ValueError if none of them does.
    """
    if isinstance(transformer, cim.PowerTransformer):
        ends, rating = transformer.PowerTransformerEnd, 'ratedU'
    elif isinstance(transformer, cim.AutoTransformer):
        ends, rating = transformer.AutoTransformerEnd, 'baseU'
    else:
        raise TypeError(f"{type(transformer).__name__} {label(transformer)} is not a transformer")

    candidates = [
        [None if end.BaseVoltage is None else end.BaseVoltage.nominalVoltage for end in ends],
        [getattr(end, rating) for end in ends],
    ]
    if isinstance(transformer, cim.PowerTransformer):
        candidates.append([winding.ratedU for tank in transformer.TransformerTanks
                           if tank.TankConfiguration is not None
                           for winding in tank.TankConfiguration.TransformerWinding])
    for voltages in candidates:
        if len(voltages) >= 2 and all(voltage is not None for voltage in voltages):
            volts = [float(voltage) for voltage in voltages]
            return any(not math.isclose(volt, volts[0], rel_tol=1e-6) for volt in volts)
    raise ValueError(f"{type(transformer).__name__} {label(transformer)}: no BaseVoltage or rating on its "
                     f"ends or tank windings, so it cannot be told from a regulator")
