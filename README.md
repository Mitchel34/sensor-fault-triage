# Sensor Fault Triage

Implementation, 27 ordinary tests, the full synthetic evaluation and [offline installation](docs/INSTALLATION.md) have passed their checks. The results include substantial limitations on weak and overlapping faults.

This project provides an offline, standard-library Python detector for probable missing, stuck, isolated-spike and sustained-offset fault windows in original synthetic multichannel streams. Events include deterministic diagnostic explanations and JSON/CSV output.

The frozen [protocol](docs/PROTOCOL.md) defines calibration isolation, exact event boundaries, matching, all seeded trials and aggregate reporting. It retains four clean controls, four clear-fault families and explicit weak/overlapping stress fixtures. [Measured results](docs/RESULTS.md) include every stratum: clear-family precision/recall were 1.00, all clean controls had zero events, and weak/overlapping faults exposed substantial misses and fragmented detections.

Designed toy fixtures do not establish accuracy on real equipment. The detector neither recommends nor performs equipment control. No private telemetry or industrial parameters are used.

## Local use

Python 3.10 or newer; no third-party runtime dependencies.

```sh
python3 sensor_cli.py --demo
python3 sensor_cli.py input.json --calibration 512
python3 sensor_cli.py input.csv --input-format csv --calibration 512 --output-format csv
python3 -m unittest discover -s tests -v
```

The demo is a separate 192-row handcrafted fixture with a missing run and isolated spike; it is not part of the 200-stream evaluation. Input JSON is a list of `{"timestamp":0,"values":{"sensor":1.2}}` rows. JSON null and empty CSV sample cells mean missing; zero is an observed measurement. CSV begins with `timestamp,sensor` (additional channel columns permitted). All timestamps must be uniformly spaced, strictly increasing integers. Calibration is an initial all-present window of at least 128 rows. See the protocol for complete bounds and rejection rules.

`sensor_core.detect(rows, calibration)` returns sorted event dictionaries. `sensor_core.fit(calibration_samples)` exposes the calibration-only baseline. The core does not read or write files. CLI validation completes before any output is written.

## Evaluation and reporting

The frozen batch consists of 20 seeds × 10 scenarios × 4 channels × 2048 timestamps. `sensor_core.evaluate()` is the self-contained entry point for a separately admitted bounded run; ordinary tests do not invoke it. A valid retained execution receipt can be exported without rerunning detection:

```sh
python3 export_results.py receipt.json results
```

The exporter retains all 97 numeric metrics, reports clear/weak/overlap event summaries, and derives scientific acceptance separately from execution success. Undefined mean delay is null in JSON and empty in CSV; misses remain explicit. Invented receipt fixtures in the tests validate exporter behavior and are not measurements.

Receipt input is limited to 1 MiB, uses strict JSON decoding and requires the supported numeric resource fields. Both JSON parsers reject nesting deeper than 64 levels. Export requires a new output directory and will not replace an earlier report. Receipt shape validation does not prove execution provenance; the admitted source and receipt linkage require separate verification.

## Offline packaging

The original standard-library builder produces a deterministic wheel with no dependencies. Build and install only as part of the separately admitted offline installation check:

```sh
python3 build_wheel.py wheel-output
python3 -m venv fresh-environment
fresh-environment/bin/python -m pip install --no-index --no-cache-dir --no-deps wheel-output/sensor_fault_triage-0.1.0-py3-none-any.whl
```

The installed command is `sensor-fault-triage`. A clean offline installation on Python 3.14.7 passed 18 installed behavior tests and CLI checks outside the source tree. The declared Python 3.10 minimum has not been tested on older interpreters. See the installation report for artifact hashes and measurement limits.

## Limits

The lag-64 baseline assumes a stable trend and compatible periodic component. Stuck detection requires exact equality and sufficient variation during calibration. Spike detection uses one neighboring sample on each side. Drift identifies sustained residual means, including offsets; general gradual drift is not validated. Missing observations break numeric windows, and overlapping faults can fragment or mask evidence. The protocol deliberately retains these difficult labels. Diagnostics can be false positives and false negatives; there is no safety validation or equipment-control integration.
