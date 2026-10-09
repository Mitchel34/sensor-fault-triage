# Measured synthetic results

One admitted evaluation executed the frozen protocol with 20 seeds, 200 streams, four channels and 2048 timestamps per stream. All 160 queued clean/clear trials and 40 stress trials were included: 1,638,400 total channel samples, 1,228,800 test observations and 960 truth labels. No thresholds, matching rules or seeds were changed after seeing results. The retained output has 97 numeric metrics, nine passing execution-integrity checks and eleven passing scientific acceptance checks.

[Full scalar results](../results/results.json) and [event summary CSV](../results/events-summary.csv) were exported from the retained receipt without importing or rerunning the evaluator. Scientific acceptance applies to the predeclared clear fixtures and noiseless controls. Stress outcomes remain part of the report.

| Stratum | Family | TP | FP | FN | Precision | Recall | Mean matched delay (samples) |
|---|---|---:|---:|---:|---:|---:|---:|
| clear | missing | 80 | 0 | 0 | 1.00 | 1.00 | 0 |
| clear | stuck | 80 | 0 | 0 | 1.00 | 1.00 | 6 |
| clear | spike | 80 | 0 | 0 | 1.00 | 1.00 | 1 |
| clear | drift | 80 | 0 | 0 | 1.00 | 1.00 | 9.0875 |
| weak/short | missing | 80 | 0 | 0 | 1.00 | 1.00 | 0 |
| weak/short | stuck | 0 | 0 | 80 | 1.00* | 0.00 | undefined |
| weak/short | spike | 0 | 0 | 80 | 1.00* | 0.00 | undefined |
| weak/short | drift | 0 | 0 | 80 | 1.00* | 0.00 | undefined |
| overlap | missing | 80 | 0 | 0 | 1.00 | 1.00 | 0 |
| overlap | stuck | 0 | 240 | 80 | 0.00 | 0.00 | undefined |
| overlap | spike | 80 | 0 | 0 | 1.00 | 1.00 | 1 |
| overlap | drift | 0 | 160 | 80 | 0.00 | 0.00 | undefined |

*Precision is defined as 1 when there are no predictions. That convention does not indicate successful detection: recall is zero and every truth event was missed. Delay is measured only for matched events, with the match counts shown as TP; unmatched events have no imputed zero delay. JSON uses null for undefined mean delay; CSV uses an empty cell.

Each clean control—constant, trend, periodic and noisy—had zero false events in 122,880 test channel-observations, or **0 per 1,000 clean observations**. Together they account for 491,520 clean test observations. This finite toy sample does not establish a zero real-world false-alarm rate.

Stuck delay is six samples on the clear fixtures because the frozen injection copies the preceding value: the maximal equal-value run begins one sample before the labelled injection. Detection needs eight equal samples, so evidence is available six samples after the truth onset. This is the declared boundary/delay convention, not a changed threshold.

Overlapping spike and missing injections fragment the stuck run and break the drift window. All original logical labels, including obscured portions, remain in truth. Predicted fragments fail the fixed IoU >=0.5 matching criterion, producing the reported false positives and misses. Weak stuck duration is below the eight-sample rule; weak spikes and offsets are below the calibrated thresholds. These failures limit applicability and are not removed from coverage.

## Resources and measurement scope

The run used local CPU with the standard library and no external service. The runner reported 4.313293 seconds wall time and 65,945,600 bytes (62.89 MiB) for the sum of worker/supervisor peak memory. The surrounding execution tool reported 4.288566 seconds wall time; these are separate observations with slightly different measurement boundaries.

Measured CPU before final receipt/database closeout was 4.241814 seconds, a lower bound on the complete operation. The ledger charged the full 60-second reservation; the exported `resources.cpu_seconds` field is this conservative charge, not the 4.24-second measurement. Worker CPU was 4.187958 seconds and the recorded supervisor component was 0.052924 seconds; these sampled components have narrower boundaries than final operation accounting.

The admitted envelope was 60 CPU-seconds, 256 MiB and 120 wall-seconds. The runner reserved closeout headroom, exposing inner limits of 59.75 CPU-seconds and 115 wall-seconds in the receipt. Memory is a conservative sum of process high-water marks, which need not occur simultaneously. It is an operational observation, not hard memory containment; sampling, scheduling and signal handling can overshoot. Evaluator-only CPU/wall timings in the metrics exclude supervisor and closeout work.

## Provenance and reproducibility

The exact evaluated core SHA256 is `613bad15257ebf5866cff0d683ad0687fd5eb518bb23c9173bf80937193cd127`. The frozen protocol SHA256 is `ce58cc143966d5cc01135cb56f896fa0233384e1fcfe173035c2f27b3e60b5a6`. The receipt SHA256 is `360cdf38f9ceaac530e7f2969be8d106afa486ba7dd3c78568c19c2d05ec9757`; the private receipt itself is excluded from the public tree. Receipt-only exporter SHA256 is `d806abe26959ad15de8585e7bddb560c27084af755c33db29e07857a015fa6ea`.

The protocol specifies every generator parameter, seed, injection, calibration rule, event boundary, match tie and denominator. The batch was run once using the actual core; results were not precomputed or reconstructed from tests. Ordinary handcrafted and invented-schema tests are separate evidence. A separate [offline installation](INSTALLATION.md) passed 18 installed behavior tests without rerunning evaluation.

Designed signals use a period compatible with the fixed lag baseline and do not represent industrial operating diversity. Sustained drift fixtures are offsets; gradual drift, varying periodicity, near-stuck noise and real telemetry are unvalidated. Clear-fixture success does not establish equipment accuracy, safety or fitness for control. The program supplies diagnostics only.
