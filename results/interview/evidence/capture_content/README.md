# Captured content mismatch evidence

These PNGs are byte-for-byte copies of saved captures, without image processing.

| File | Original run and frame | Meaning |
|---|---|---|
| `box_product20_previous.png` | `baseline/after_20261029_210305/box_2/runs/20261029_210546_782130200_seed42/frames/P_0020.png` | Previous product, orange/color defect |
| `box_product21_received.png` | `baseline/after_20261029_210305/box_2/runs/20261029_210546_782130200_seed42/frames/P_0021.png` | Image delivered for the next good product; identical to product 20 |
| `box_product21_reference.png` | `baseline/after_20261029_210305/box_1/runs/20261029_210402_399861200_seed42/frames/P_0021.png` | Correct blue image for product 21 from the first repetition |

Original paths are relative to `results/interview/`. SHA256 values are in `sha256.json`.

The failed request and returned SWH numbers both equal 2517. The previous capture's SWH is 2427. RGB digests, original paths, and offline label conflict are recorded in `../../capture_duplicate_audit.json`; the corresponding trace and inspection CSVs are versioned under the original runs.

The inspector classified the received orange pixels as a color defect. Ground-truth labels were used only for offline diagnosis. Matching frame numbers did not establish matching image content in this case. The native root cause remains unresolved; successful controlled reruns do not prove its resolution.
