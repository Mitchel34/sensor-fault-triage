# Sensor Fault Triage protocol v2 — proposed for review

No implementation or measurements exist yet. Freeze this document before source authoring. Changes after a passed gate require reviewed reconciliation. This is an offline diagnostic exercise on original toy signals, with no equipment action or real-equipment accuracy claim.

## Contracts

The pure core accepts a list of row dictionaries with exactly `timestamp` and `values`. Timestamp is an integer (not Boolean), strictly increasing, nonnegative, at most 10^9. Values is a dictionary of 1–16 channel names matching ASCII `[a-z][a-z0-9_]{0,31}`; the channel set is identical in every row. Numeric samples are int/float, excluding Boolean, finite, absolute magnitude <=10^9; only None represents missing. No implicit zero filling. Rows number 129–100000. Core validates the whole input before returning any result. Calibration length is an explicit integer, 128–4096, less than row count. Calibration timestamps must be uniformly spaced, with a positive integer step, and all subsequent timestamps must continue that grid. No duplicate, unordered, absent, coerced or nonfinite timestamp is accepted. All calibration samples must be present. Invalid data raises ValueError with deterministic reason; wrappers print a bounded message and exit nonzero without partial output.

Use sample indices internally. All fault intervals are half-open `[start_index,end_index)` in original row coordinates. Output events contain exactly channel, fault_type (missing/stuck/spike/drift), start_index, end_index, start_time, end_time, detected_index, score, explanation. End_time is the timestamp at end_index, or last timestamp plus the established step for terminal events. Score is finite and nonnegative. Sort events by channel lexicographically, start_index, end_index, then fault_type lexicographically. Explanations have fixed wording and six-decimal numeric formatting; no recommendations. JSON output uses allow_nan=False and sorted keys. CSV has fixed columns in the listed order. JSON/CSV parsing, writing and hashing remain outside the core. JSON duplicate object keys and nonstandard NaN/Infinity literals are rejected. CSV has header timestamp plus channel columns; an empty sample field means missing; other invalid or empty timestamps fail. CLI calibration length is mandatory except the explicitly identified demo.

Arithmetic uses bounded finite inputs and explicitly validates derived baseline/threshold/score values; overflow/nonfinite intermediates fail, never emit NaN. Supported value/timestamp bounds are conservative input limits, not a sensor model.

## Calibration and detector rules

Fit each channel from calibration samples alone. With lag L=64, slope b is median of `(y[i]-y[i-L])/L` for i=L..C-1. Intercept a is median of `y[i]-b*i` for i=0..C-1. Residuals r[i]=y[i]-(a+b*i). Scale s=max(0.01,1.4826*median(abs(r-median(r)))). Calibration dynamic range d=max(y)-min(y). Freeze a,b,s,d before observing the test window. There is no refit, update, cross-channel pooling, future calibration access, or test-fitted threshold. This lag model is a transparent designed-fixture assumption, not a universal periodicity estimator.

Run rules independently on the test window; events can overlap across types. Missing breaks each numeric run/window. Never merge across a missing sample, test boundary or a gap in a rule's active samples.

* Missing: every maximal contiguous run of None, including single samples. Score=run length; detected_index=start.
* Stuck: each maximal run of exactly equal finite values with length >=8, only when calibration d>1e-8. Emit the entire run. Score=length/8; detected_index=start+7. Exact equality is deliberate; near-stuck noise is outside this rule. Constant calibrated channels are not automatically faults.
* Spike: for each interior test sample with both immediate neighbors present, require abs(y[i]-(y[i-1]+y[i+1])/2)>8s and abs(y[i+1]-y[i-1])<=2s. Emit [i,i+1), score=first absolute deviation/(8s), detected_index=i+1. First/last test samples cannot be isolated spikes by this definition.
* Drift: trailing 32-sample windows entirely inside the test set and entirely present. At endpoint i, active if abs(mean(residual[i-31:i+1]))>4s. Group contiguous active endpoints into events [first_active,last_active+1). Score=max active absolute mean/(4s). detected_index=first_active. Do not backdate onset or subtract detection latency. Drift can persist for up to 31 samples after an injection; boundaries intentionally reflect detector evidence.

Offline event finalization may inspect the complete test sequence. `detected_index` records the earliest row where onset evidence exists under these rules, not wall latency or a claim of a streaming implementation. Stuck boundary backdating is explicit; spike uses one sample of lookahead.

## Frozen original generator and workload

Seeds are integers 0..19 inclusive. Every stream has four channels c0..c3 and 2048 timestamps t=0..2047. Calibration [0,512); scoring/test [512,2048). Every trial includes all channels. Generate each stream using its own `random.Random(seed*1000+scenario_id*10+channel_index)` per channel; draw random.gauss(0,noise_sigma) once per timestamp, including sigma=0. Original clean formula is `10+2*j + trend*t + amplitude*sin(2*pi*t/64 + j*pi/4) + noise`. No source data or industrial parameters are used.

Scenario ids 0..9 are immutable:

| id | scenario | trend | amplitude | noise sigma | injection |
|---|---|---:|---:|---:|---|
| 0 | clean_constant | 0 | 0 | 0 | none |
| 1 | clean_trend | .0005 | 0 | 0 | none |
| 2 | clean_periodic | .0005 | .2 | 0 | none |
| 3 | clean_noisy | .0005 | .2 | .02 | none |
| 4 | clear_missing | .0005 | .2 | .02 | None on [900,932) |
| 5 | clear_stuck | .0005 | .2 | .02 | replace [1000,1064) with original y[999] |
| 6 | clear_spike | .0005 | .2 | .02 | add +4 at 1100 |
| 7 | clear_drift | .0005 | .2 | .02 | add +3 on [1200,1360) |
| 8 | low_amplitude | .0005 | .2 | .02 | all four weak/short faults below |
| 9 | overlap | .0005 | .2 | .02 | all four overlapping faults below |

Apply each injection identically in interval and amplitude to all four channels, retaining independent generated noise. Clear truth is one event per channel of the named family. Drift is a sustained offset rather than a gradual ramp; general gradual drift is a documented limitation.

Low-amplitude/short fixture: missing [800,801); stuck [900,904) at original y[899]; spike +0.15 at 1050; drift +0.15 on [1200,1360). Missing has no numeric amplitude; its one-sample duration is the explicit weak counterpart. Stuck duration four is intentionally below the rule. All 16 labels per stream remain in truth.

Overlap fixture: drift +3 on [1000,1200), then stuck replacement [1050,1114) at the drift-modified y[1049], then spike +4 at 1080, then missing [1090,1106). Keep all four original logical truth intervals, including portions occluded by later injections. Ordering is fixed and makes overlap/masking difficulty explicit. Do not delete occluded labels. Stress failure is reportable and does not change clear-fixture acceptance.

Totals: 160 queued streams (80 clean, 80 clear-fault), plus 40 stress streams =200 streams; 800 channel-streams; 1,638,400 samples including calibration; 1,228,800 test channel-observations; 491,520 clean-control test observations. Clear truth 80 per family, 320 total. Each stress stratum has 80 truth events per family, 320 total; all truth totals 960. No reductions, seed selection or fallback batch. Freeze injections before any threshold fitting. Generate in memory, process one stream at a time and discard it after aggregate accounting. No evaluator I/O.

## Matching, delays and denominators

Match separately within trial, channel and exact family. No cross-trial/channel/type matches. Intersection is count of shared integer sample indices, union=end_max-start_min for overlapping intervals. Candidate eligibility requires positive overlap and intersection/union >=0.50, inclusive; this is the complete overlap tolerance, with zero endpoint padding. Sort candidate pairs by decreasing IoU, increasing absolute start difference, increasing truth start/end, increasing prediction start/end, then truth index and prediction index in their sorted event lists. Greedily accept a pair only if both events remain unmatched. This deterministic one-to-one greedy convention is fixed; it is not claimed to maximize matching cardinality.

TP=matched pair count, FP=unmatched predictions, FN=unmatched truth. Precision TP/(TP+FP), with 1 when denominator zero; recall TP/(TP+FN), with 1 when denominator zero. Clear-family precision includes all predictions of that family on all 80 clear streams, including off-family false alarms. Clean-control events are reported separately; stress predictions are kept in their own stratum. Delay=max(0,prediction.detected_index-truth.start_index) samples for matched pairs only. Publish matched count and missed count beside mean delay; misses are FN and are never assigned zero delay or removed from recall. Delay mean is zero if there are no matches and explicitly labelled undefined in human reports. No censored delay is represented as a successful detection.

Clean false-event rate=1000*all predicted events on that clean scenario / all its test channel-observations (122880 per scenario); count each event, even overlapping types. Missing samples in fault fixtures remain part of test coverage; clean denominator contains no missing data. No accepted target for noisy clean or stress; always publish all counts and derived rates.

## Exact runner output budget

The sole self-contained stdlib core includes detector, generator, matcher and evaluate(). It returns only `metrics` and nonempty `checks`. Serialization/export tools consume the genuine saved receipt without calling evaluate(). Demo uses an independently identified small handcrafted fixture and is never evidence for the batch.

Freeze 97 numeric metrics, each an ordinary scalar with a documented unit (no packing):

* For each prefix clear, low, overlap and each family missing, stuck, spike, drift: `{prefix}_{family}_{tp,fp,fn,delay_sum,delay_n}` =60 metrics. delay_sum is sample count, delay_n is matches.
* Clear precision/recall for each family: `clear_{family}_{precision,recall}` =8.
* For each clean prefix constant, trend, periodic, noisy: `clean_{prefix}_{events,observations,per_1000}` =12.
* Coverage: `streams`, `channel_streams`, `observations`, `test_observations`, `clean_streams`, `clear_streams`, `low_streams`, `overlap_streams`, `clear_truth`, `low_truth`, `overlap_truth`, `seeds`, `channels`, `timestamps`, `calibration_samples` =15. calibration_samples=512 is per channel, not total.
* `evaluation_cpu_seconds` and `evaluation_wall_seconds` =2, measured inside evaluate with process_time/perf_counter. These are evaluator-only measures; the genuine runner receipt supplies worker/supervisor measurements, memory, conservative CPU charge, limits and operational monitoring caveats separately.

Separate execution/data integrity from scientific acceptance. The unchanged runner discards its result (`result:null`, exit 95) if any runner check is false. Therefore scientific targets must not be runner checks. A completed runner operation with retained metrics does not establish scientific acceptance.

The exact return shape is `{"metrics": {metric_name: finite_number, ...}, "checks": [{"name": check_name, "passed": bool}, ...]}`. Return exactly the following nine runner checks, in this order. Here m is the actual computed metrics dictionary; counters must accumulate from actual processed streams rather than prefilled totals.

| runner check name | exact predicate |
|---|---|
| streams_complete | m["streams"] == 200 |
| channel_streams_complete | m["channel_streams"] == 800 |
| observations_complete | m["observations"] == 1638400 |
| test_observations_complete | m["test_observations"] == 1228800 |
| clean_streams_complete | m["clean_streams"] == 80 |
| clear_streams_complete | m["clear_streams"] == 80 |
| stress_streams_complete | m["low_streams"] == 20 and m["overlap_streams"] == 20 |
| truth_complete | m["clear_truth"] == 320 and m["low_truth"] == 320 and m["overlap_truth"] == 320 |
| metric_count_complete | len(m) == 97 |

Every trial enters aggregates once; static/ordinary tests verify scenario enumeration and counter logic without executing the full batch. The runner's existing schema/finite-number/resource checks remain unchanged. A false integrity check or execution/resource failure is retained as such, with its genuine receipt and possibly unavailable metrics. Never reconstruct missing measurements, relabel an integrity failure as a scientific miss, or rerun to replace it.

After a successful execution/integrity receipt, a separate outside-core evaluation-gate/export wrapper consumes the genuine receipt metrics without importing/calling evaluate(), running the detector or generating streams. It derives exactly these eleven scientific checks with the same `{name:string,passed:bool}` shape, ordered by family missing, stuck, spike, drift (precision then recall), then clean constant, trend, periodic:

* `clear_{family}_precision_target`: TP/(TP+FP) >=0.80, using m["clear_{family}_tp"] and m["clear_{family}_fp"], with precision=1 if TP+FP=0.
* `clear_{family}_recall_target`: TP/(TP+FN) >=0.80, using m["clear_{family}_tp"] and m["clear_{family}_fn"], with recall=1 if TP+FN=0.
* `clean_{control}_zero_events`: m["clean_{control}_events"] ==0.

The brace notation expands to exact identifiers, e.g. `clear_missing_precision_target` and `clean_constant_zero_events`; it is not a literal output name. Report derived precision/recall alongside the corresponding stored metrics and reject any inconsistency as an integrity problem. These eleven checks are separate from, and never inserted into, the runner's nine checks. Any false scientific check must produce `outcome:fail` evaluation-gate evidence, preserve all actual Boolean results and genuine numerical metrics, and leave delivery incomplete. Retain the successful execution receipt and failed scientific gate together. Do not tune thresholds, matching, injections or seeds, rerun the workload, or change the runner to obtain a pass. Noisy-clean and all stress outcomes are exported regardless of scientific acceptance. No hidden encoding or precomputed measurements.

## Validation and delivery plan

After coordinator and independent plan review, author original pure core, CLI wrappers and hand-built unittest fixtures. Tests cover each rule, all four clean forms, exact threshold and boundary cases, missing breaks, constant calibration, malformed rows, channel mismatch, duplicate/nonuniform timestamps, nonfinite/overflow bounds, insufficient/missing calibration, duplicate JSON keys, CSV missing semantics, calibration isolation and deterministic events/explanations. Fit must be unchanged when only test data changes; no test fixture calls evaluate or loops through the admitted 200-stream workload. Independent code/test/protocol review precedes implementation/tests gate acceptance, with findings retained and resolved. Ordinary tests use one CPU, <=256 MiB and <=60 CPU/wall seconds; operational bounds are not hard RSS containment.

Evaluation requires a fresh exact reviewed operation and resource admission; execute the unchanged production runner once. Never retry uncertain execution. Export measured JSON/CSV tables from that exact receipt. Installation then requires its own reviewed once-only offline operation using installed tools, disabled indexes/caches, a fresh private environment, and installed behavior checks outside source. Source/artifact digests are recorded. Do not create package dependencies, license declarations or hosted workflows.

Documentation will explain provenance, architecture, reproduction, every metric including stress and noisy controls, resources and limitations. Publication requires exact content/full-history/commit review and independent remote byte/tree/history verification. Until then, no public repository creation or push. No safety validation, industrial integration or action advice is in scope.
