# Interview verification results

Generated from raw artifacts. Missing experiments remain unmeasured.

## Before/after outcome regression

| part | repeat | identical outcomes |
|---|---|---|
| box | 1 | True |
| box | 2 | True |
| crown | 1 | True |
| crown | 2 | True |
## Captured content investigation

- Identical consecutive capture pairs: 1; conflicting offline expected labels: 1.
- Frame number equality does not establish image/state equality. See capture_duplicate_audit.json for raw paths and hashes.
- The historical content mismatch has an unresolved native root cause; successful controlled reruns do not establish its resolution.
- Offline expected labels are used for diagnosis only; no ground truth enters runtime inspection.

- Composition: 5 asserted checks passed (20261026_224502).
- Composition: 5 asserted checks passed (20261026_225331).

## Repeated CAD assets

| mode | count | CPU open ms (median) | CPU RSS MiB (median) | Kit update p50 ms | Kit update p95 ms | render runs |
|---|---|---|---|---|---|---|
| reference | 10 | 18.52 | 65.1 | 10.320000001229346 | 11.42674993025139 | 3 |
| instance | 10 | 32.82 | 65.0 | 10.18920005299151 | 11.23946500592865 | 3 |
| deinstanced | 10 | 9.57 | 65.2 | 10.257249989081174 | 11.306129937293008 | 3 |
| reference | 50 | 20.36 | 66.3 | 10.161400015931576 | 11.443595052696764 | 3 |
| instance | 50 | 30.93 | 65.2 | 10.125700035132468 | 11.243019928224385 | 3 |
| deinstanced | 50 | 19.85 | 66.1 | 10.149449983146042 | 11.490595049690455 | 3 |
| reference | 100 | 37.64 | 67.4 | 10.234199988190085 | 11.47900497308001 | 3 |
| instance | 100 | 33.46 | 65.6 | 10.248799982946366 | 11.499920021742582 | 3 |
| deinstanced | 100 | 27.31 | 67.0 | 10.225650039501488 | 11.589889990864322 | 3 |

## Kit loading and memory (medians)

| mode | count | stage open ms | first viewport frame s | process RSS MiB | whole-device GPU MiB |
|---|---|---|---|---|---|
| reference | 10 | 669.737899908796 | 8.207846699981019 | 5551.359375 | 3198 |
| instance | 10 | 668.6488999985158 | 8.285131499986164 | 5584.296875 | 3199 |
| deinstanced | 10 | 617.2476001083851 | 8.20919209998101 | 5561.8828125 | 3193 |
| reference | 50 | 679.6126998960972 | 8.145737299928442 | 5574.4453125 | 3193 |
| instance | 50 | 654.3474000645801 | 8.110016599996015 | 5566.47265625 | 3199 |
| deinstanced | 50 | 720.8045000443235 | 8.376812000060454 | 5576.1875 | 3193 |
| reference | 100 | 703.6219000583515 | 8.52555390005 | 5611.9296875 | 3193 |
| instance | 100 | 626.7138998955488 | 8.517073699971661 | 5555.21484375 | 3198 |
| deinstanced | 100 | 744.4522000150755 | 8.472877799998969 | 5600.27734375 | 3200 |

## Timing conditions (repetitions reuse the configured seed)

| condition | runs | RTF median | capture p95 median ms | route correct / total | timeouts | fail-safe rejects |
|---|---|---|---|---|---|---|
| delivery_delay | 3 | 1.090 | 512.4724749475718 | 18/18 | 0 | 0 |
| fixed_heavy | 3 | 0.613 | 212.48405004735105 | 18/18 | 0 | 0 |
| fixed_light | 3 | 1.013 | 128.47175006754696 | 18/18 | 0 | 0 |
| update_budget | 3 | 1.081 | None | 9/18 | 18 | 18 |
| wall_heavy | 3 | 1.001 | 201.42364999628626 | 18/18 | 0 | 0 |
| wall_light | 3 | 1.001 | 128.84897497133352 | 18/18 | 0 | 0 |
| wall_timeout | 3 | 1.085 | None | 9/18 | 18 | 18 |

## Timing runs

| run | status | wall s | RTF | capture p95 ms | max pending | correct/sorted | timeouts | late |
|---|---|---|---|---|---|---|---|---|
| results\interview\timing\20261026_231543\delivery_delay_1\runs\20261026_232335_690003200_seed42\timing.json | complete | 10.340275 | 1.0992615232041993 | 511.6059749852866 | 1 | 6/6 | 0 | 0 |
| results\interview\timing\20261026_231543\delivery_delay_2\runs\20261026_232406_908944300_seed42\timing.json | complete | 10.682683 | 1.0640273097936577 | 516.7137250246014 | 1 | 6/6 | 0 | 0 |
| results\interview\timing\20261026_231543\delivery_delay_3\runs\20261026_232438_447279800_seed42\timing.json | complete | 10.430578 | 1.089744669529428 | 512.4724749475718 | 1 | 6/6 | 0 | 0 |
| results\interview\timing\20261026_231543\fixed_heavy_1\runs\20261026_231753_631086300_seed42\timing.json | complete | 18.75769 | 0.6059736986730965 | 218.57615001499653 | 1 | 6/6 | 0 | 0 |
| results\interview\timing\20261026_231543\fixed_heavy_2\runs\20261026_231841_084216600_seed42\timing.json | complete | 18.537905 | 0.6131581031754177 | 212.48405004735105 | 1 | 6/6 | 0 | 0 |
| results\interview\timing\20261026_231543\fixed_heavy_3\runs\20261026_231925_747552900_seed42\timing.json | complete | 18.089847 | 0.628345100400776 | 209.22797502134927 | 1 | 6/6 | 0 | 0 |
| results\interview\timing\20261026_231543\fixed_light_1\runs\20261026_231606_936439300_seed42\timing.json | complete | 11.45768 | 0.9920565912378196 | 152.42867494816892 | 1 | 6/6 | 0 | 0 |
| results\interview\timing\20261026_231543\fixed_light_2\runs\20261026_231641_570316500_seed42\timing.json | complete | 11.210854 | 1.01389835813936 | 128.47175006754696 | 1 | 6/6 | 0 | 0 |
| results\interview\timing\20261026_231543\fixed_light_3\runs\20261026_231716_141983700_seed42\timing.json | complete | 11.226144 | 1.0125174293333292 | 125.28010000823997 | 1 | 6/6 | 0 | 0 |
| results\interview\timing\20261026_231543\update_budget_1\runs\20261026_232646_593744100_seed42\timing.json | complete | 9.587366 | 1.0812841035122156 | None | 1 | 3/6 | 6 | 0 |
| results\interview\timing\20261026_231543\update_budget_2\runs\20261026_232718_399051700_seed42\timing.json | complete | 9.584308 | 1.0816291691998057 | None | 1 | 3/6 | 6 | 0 |
| results\interview\timing\20261026_231543\update_budget_3\runs\20261026_232748_811110900_seed42\timing.json | complete | 9.741891 | 1.0641328616127335 | None | 1 | 3/6 | 6 | 0 |
| results\interview\timing\20261026_231543\wall_heavy_1\runs\20261026_232150_183562900_seed42\timing.json | complete | 11.36446 | 1.0010188077789828 | 198.7912000331562 | 1 | 6/6 | 0 | 0 |
| results\interview\timing\20261026_231543\wall_heavy_2\runs\20261026_232229_792447400_seed42\timing.json | complete | 11.357477 | 1.000871434763244 | 201.42364999628626 | 1 | 6/6 | 0 | 0 |
| results\interview\timing\20261026_231543\wall_heavy_3\runs\20261026_232303_608636900_seed42\timing.json | complete | 11.380635 | 1.0006161958328745 | 204.40389995928854 | 1 | 6/6 | 0 | 0 |
| results\interview\timing\20261026_231543\wall_light_1\runs\20261026_232008_375530800_seed42\timing.json | complete | 11.371932 | 1.000622277751634 | 128.84897497133352 | 1 | 6/6 | 0 | 0 |
| results\interview\timing\20261026_231543\wall_light_2\runs\20261026_232042_359635400_seed42\timing.json | complete | 11.364567 | 1.001237865006006 | 133.48500008578412 | 1 | 6/6 | 0 | 0 |
| results\interview\timing\20261026_231543\wall_light_3\runs\20261026_232114_654095200_seed42\timing.json | complete | 11.362109 | 1.000811794691857 | 122.16522498056293 | 1 | 6/6 | 0 | 0 |
| results\interview\timing\20261026_231543\wall_timeout_1\runs\20261026_232509_908742100_seed42\timing.json | complete | 9.759076 | 1.062259058033842 | None | 1 | 3/6 | 6 | 0 |
| results\interview\timing\20261026_231543\wall_timeout_2\runs\20261026_232542_544459200_seed42\timing.json | complete | 9.471296 | 1.0945351678529565 | None | 1 | 3/6 | 6 | 0 |
| results\interview\timing\20261026_231543\wall_timeout_3\runs\20261026_232614_339324300_seed42\timing.json | complete | 9.552 | 1.0852875488657678 | None | 1 | 3/6 | 6 | 0 |
| results\interview\baseline\after_20261026_233733\box_1\runs\20261026_233756_279165900_seed42\timing.json | complete | 58.57093 | 0.941024278377309 | 145.24477004888467 | 1 | 30/30 | 0 | 0 |
| results\interview\baseline\after_20261026_233733\box_2\runs\20261026_233916_283357600_seed42\timing.json | complete | 57.919202 | 0.9516130123132308 | 139.91994498646818 | 1 | 30/30 | 0 | 0 |
| results\interview\baseline\after_20261029_210305\box_1\runs\20261029_210402_399861200_seed42\timing.json | complete | 69.808161 | 0.7895447471330547 | 168.43492499829154 | 1 | 30/30 | 0 | 0 |
| results\interview\baseline\after_20261029_210305\box_2\runs\20261029_210546_782130200_seed42\timing.json | complete | 68.176157 | 0.8084449046827716 | 172.6067050025449 | 1 | 29/30 | 0 | 0 |
| results\interview\baseline\after_20261029_210305\crown_1\runs\20261029_210911_533143500_seed42\timing.json | complete | 174.927894 | 1.5794126814509697 | 166.79984000511467 | 5 | 13/30 | 125 | 0 |
| results\interview\baseline\after_20261029_211839\box_1\runs\20261029_211859_078875200_seed42\timing.json | complete | 57.822209 | 0.9532092862683939 | 136.50559999223333 | 1 | 30/30 | 0 | 0 |
| results\interview\baseline\after_20261029_211839\box_2\runs\20261029_212017_851084500_seed42\timing.json | complete | 57.891017 | 0.9520763192163639 | 136.50579000241123 | 1 | 30/30 | 0 | 0 |
| results\interview\baseline\after_20261029_211839\crown_1\runs\20261029_212136_597790900_seed42\timing.json | complete | 303.766464 | 0.9194014693254873 | 155.45279999787454 | 1 | 30/30 | 0 | 0 |
| results\interview\baseline\after_20261029_211839\crown_2\runs\20261029_212701_138627000_seed42\timing.json | complete | 303.053632 | 0.9215640519264285 | 151.60965500108432 | 1 | 30/30 | 0 | 0 |

## Lifecycle

- after: 5 checks, stale callbacks applied=0, expected behavior verified=True
- after: 50 checks, stale callbacks applied=0, expected behavior verified=True
- before: 10 checks, stale callbacks applied=10, expected behavior verified=True
- Native pending: 40 checks, callback pending before transition=40, passed=True
- Native pending: 40 checks, callback pending before transition=40, passed=True

## LOD (50 instances)

| LOD | render runs | update p50 ms | update p95 ms | Kit RSS MiB median |
|---|---|---|---|---|
| 0 | 3 | 10.16594999236986 | 11.188484991726 | 5556.78515625 |
| 3 | 3 | 10.287349992722739 | 11.372164992644684 | 5546.25 |
| 4 | 3 | 10.313049991964363 | 12.422614996467018 | 5567.26953125 |

## Frame content

- 20261026_231452: samples=30, mismatches=0, undecodable=0, errors=0

## Measurement limits

- Kit update intervals include CPU and rendering; they are not GPU-only frame durations.
- GPU memory snapshots are device-wide, not per-process VRAM.
- Fresh process does not imply cold OS, shader or driver caches.
- Instancing can trade editing flexibility for sharing; no speedup is assumed.
- Timing p95 excludes timed-out requests; event counts must be read alongside latency.
- Raw verdict latency starts at the final callback's capture request; product_verdict_ms in report.json uses the product's first capture request.
