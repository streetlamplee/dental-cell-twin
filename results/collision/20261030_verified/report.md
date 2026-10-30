# Robot collision preflight

Status: clear_at_samples

Conservative geometry boxes; discrete sampling, not continuous/mesh collision proof.

Robot boxes: 34; environment boxes: 37
Max time step: 0.00833333333333333s; max angular step: 1.0 deg; box padding: 0.0 mm.

| Phase | Samples |
|---|---|
| load | 609 |
| unload | 554 |
| inspection_wait | 1380 |

## First overlap per pair and phase

| Phase | Time (s) | Robot | Obstacle |
|---|---|---|---|

Excluded: robot self-collision; carried products; machine vs environment; manual/teach motion; base_link vs mounting pedestal

OBB overlap may be a false positive for non-box geometry
discrete samples do not prove continuous collision freedom
report is a snapshot; stage edits require a new preflight
