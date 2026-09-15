# Unrated tank transformers are misclassified as voltage regulators

**Layer:** switch/secondary area construction (`ConnectivityArea`) — *not* islanding
**Component:** `cimtopology/distribution/distributed_topology.py::check_boundary`
**Status:** open, awaiting a decision on the tie-breaker signal
**Found:** 2026-09-14

## Symptom

`create_secondary_areas` builds one secondary area on the ieee13 fixture where it
should build two. The poletop distribution transformer `tpoletop` is crossed by the
spanning tree instead of bounding an area, so the low-voltage lateral behind it is
absorbed into the parent switch area.

Observed on ieee13:

| transformer | ratings | `check_boundary` | correct? |
| --- | --- | --- | --- |
| `xfm1` | `PowerTransformerEnd` 4160 / 480 | `True` | yes |
| `sub3` | `PowerTransformerEnd` 115000 / 4160 / 13200 | `True` | yes |
| `Reg` | none populated | `False` | yes, but by luck |
| `tpoletop` | none populated | `False` | **no** — should bound a secondary area |

Resulting area counts: `{distributionArea: 1, feederArea: 1, switchArea: 4,
secondaryArea: 1}`. The reference topology for this fixture has two secondary areas.

## Scope note

This is a **static** planning artifact: switch areas are built by treating every
controllable switch as open and growing a spanning tree to the next switch. It has
nothing to do with `TopologicalIsland`, which is a real-time artifact derived from
SCADA switch state. Island counts, orphan `ConnectivityNode` counts and angle
references are all insensitive to this defect and must not be used to verify a fix —
they cannot move when `check_boundary` changes.

## Root cause

`check_boundary` decides "regulator vs. step-down" by comparing winding voltages and
treating equal ratings as a regulator (crossed). Voltages are collected up a ladder of
sources, gated by a `found_voltages` flag so that later rungs are skipped once one
yields data.

The flag is set unconditionally inside the collection loop, and the value appended is
not checked for `None`:

```python
for end in tank.TransformerTankInfo.TransformerEndInfos:
    voltages.append(end.ratedU)      # may be None
    found_voltages = True            # set even when it was None
if len(set(voltages)) == 1:
    is_boundary = False
```

When a rung exists but is unpopulated, `voltages` fills with `None`, `found_voltages`
short-circuits the remaining rungs, and `len(set([None, None])) == 1` reads as
"windings match" — i.e. regulator. So **"no ratings available" is indistinguishable
from "equal ratings"**, and every unrated tank transformer is silently classified as a
regulator and crossed.

This also defeats the intended conservative default. The function opens with
`is_boundary = True` specifically so that a transformer with no readable ratings stays
a boundary (a missed boundary silently merges two voltage levels, which is worse than
a spurious one). The `None`-equality collapse overrides that default.

Note this is a logic defect on *any* profile, not a profile-compatibility issue.

## Why the obvious fixes are not sufficient

Neither candidate separates `Reg` from `tpoletop` on ieee13, because that fixture
carries no ratings for **either** transformer at any rung:

- **Skip `None` when collecting** (only set `found_voltages` for real values). Makes
  `tpoletop` a boundary — correct — but also flips `Reg` to a boundary, creating a
  spurious secondary area at the regulator.
- **Skip `None`, and add `TransformerTankEnd.ratedU` as a rung.** That field is
  populated on real tank-modelled exports (step-down pairs such as 24900/12470) and is
  the direction the draft CIM18 transformer model moves toward, so it is worth adding
  on its own merits. But on ieee13 both `Reg` and `tpoletop` remain all-`None` at every
  rung, so it does not resolve this case.

Separating them requires a signal other than winding voltage. Candidates:

1. **`RatioTapChanger` presence** — a regulator has one, a distribution transformer
   does not. Cheap, and already how the fixture distinguishes them visually.
2. **`TransformerTankEnd.phaseNeutralU`** — carries 7200 / 120 in the CIM18 sketch
   where `ratedU` is absent.

Option 1 is the likely answer but is unconfirmed against real models.

## Fix constraints

The voltage ladder in `check_boundary` was hand-tested and verified against multiple
CIM100 variations. Do not restructure it. Two changes were already made purely for
cimhub_2026 compatibility, with no logic change, because rungs 2 and 3 otherwise raise
`AttributeError` rather than returning nothing:

- `TransformerEndInfo.ratedU` was renamed to `ratedVoltage` in 2026 — read via the
  `_end_info_rated_u` shim.
- `TransformerTank.Assets` was dropped in 2026 — guarded with `getattr`, matching how
  the sibling `TransformerTankInfo` rung was already guarded.

## Regression check for a fix

Count `ConnectivityArea` objects by `areaType` after
`create_feeder_area` → `create_switch_areas` → `create_secondary_areas` on ieee13, and
assert `secondaryArea == 2` with `Reg` absent from the boundary set. Do **not** assert
on island or orphan counts; see the scope note above.

There is currently no test covering secondary-area counts. One should be added with
the fix.
