"""Build the ConnectedAreas of a cim18v17 feeder: feeder, switch and secondary areas.

The cim18v17 port of cim17 ``distributed_feeder.create_distributed_feeder``. It works in place on the
FeederModel and is safe to run again: the areas of a previous build are deleted first.

cim17 also made a DistributionArea from the substation's Region and linked Feeder.FeederArea; those
classes are gone in cim18v17, so the feeder area is the top of the tree here.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from cimtopology.cim18.areas import clear_areas, find_cuts
from cimtopology.cim18.feeder_area import create_feeder_area
from cimtopology.cim18.index import index_model
from cimtopology.cim18.secondary_area import create_secondary_areas
from cimtopology.cim18.switch_area import create_switch_areas

if TYPE_CHECKING:
    from cimgraph.models import FeederModel


def build_connected_areas(feeder_model: FeederModel):
    """Build every area of the feeder and return the feeder area (the others are ``ContainedArea``)."""
    clear_areas(feeder_model)
    index = index_model(feeder_model)
    cuts = find_cuts(index, feeder_model.cim)
    feeder_area = create_feeder_area(feeder_model, index, cuts)
    for switch_area in create_switch_areas(feeder_model, index, cuts, feeder_area):
        create_secondary_areas(feeder_model, index, cuts, switch_area)
    return feeder_area
