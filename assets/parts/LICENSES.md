# Third-party CAD parts — attribution and licenses

Parts here are used as conveyor products in the VisionTwin simulation. Sources, hashes and
selection status: `sources.json`. Download again with `scripts/fetch_parts.ps1`.

## KFL08 (2-bolt flange bearing unit, 8 mm bore)

| | |
|---|---|
| Title | KFL08 |
| Author | **hasecilu** (FreeCAD-library commit `b7b292a783`, 2022-02-24, "KFL08 added") |
| Source | https://github.com/FreeCAD/FreeCAD-library/blob/f5ca01cdcaa2f69b9295a6382719c2d90628780c/Mechanical%20Parts/Mountings/KFL08/KFL08.step |
| License | Creative Commons Attribution 3.0 Unported (CC-BY-3.0), see https://github.com/FreeCAD/FreeCAD-library/blob/master/LICENSE-Assets and https://creativecommons.org/licenses/by/3.0/ |
| Original file | `raw/kfl08.step` (unmodified, SHA256 in `sources.json`) |

**Changes made (adaptations in `usd/`):**
- `usd/kfl08.usd`: converted from STEP to USD with the NVIDIA Omniverse CAD converter (`omni.kit.converter.hoops_core` 512.2.1, options in `config/cad_converter_options.json`).
- `usd/kfl08_good.usda`, `_color.usda`, `_missing.usda` (reference + override layers, built by `scripts/make_part_variants.ps1`):
  - rotated so the bearing axis is vertical, uniformly scaled ×4.167 (longest side 0.2 m), placed with the bottom at z = 0;
  - the housing is repainted for the simulation (blue in `good`/`missing`, orange in `color`);
  - `missing` deactivates the bearing insert (rings, seals, balls, cages, rivets) to model a missing-part defect.

These changes are ours. The original author does not endorse this project.

## Not used

See `sources.json` (`status` and `reason`). A KiCad 3D model was rejected because its file header (GPL-3.0-or-later + exception) and its repository license (CC-BY-SA-4.0 + exception) disagree.
