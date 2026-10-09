# Verified offline installation

Version 0.1.0 was built and installed once in a fresh private environment using the original standard-library wheel builder and locally bundled pip 26.2.1. Python **3.14.7** was tested. Python 3.10 is the declared minimum, but older versions were not tested.

No network, package index, dependency download or external build dependency was used. The wheel contained six verified entries; ten installed RECORD entries were verified. Installed module bytes matched the reviewed source, and imports resolved inside the fresh environment while checks ran outside the source tree.

All **18 installed behavior tests passed**, with no failures or skips. Evaluation and generator calls were guarded; neither the evaluation nor the source receipt-exporter tests were rerun in this installation stage. Installed module and console-entry-point checks passed in JSON and CSV modes on the separate 192-row demo, with exactly two expected events. Duplicate-key input returned exit code 2 and zero stdout bytes.

The wheel `sensor_fault_triage-0.1.0-py3-none-any.whl` had SHA256 `b6e973b8e14eb510271f7f042317c76435b159c03b879eb2573c55187fd62457`.

| Frozen input | SHA256 |
|---|---|
| sensor_core.py | 613bad15257ebf5866cff0d683ad0687fd5eb518bb23c9173bf80937193cd127 |
| sensor_cli.py | a392dff1bb064c95c89b3438a0a81d6726505a31d2ca011c446e05a1011ae326 |
| build_wheel.py | ac9f1180d57b39453336eebfa26293cd6ec7efe400343e0c09131572fe81c667 |
| tests/test_behavior.py | 72050bf2dde4221bbee1e779a30f5bae2511ba9a5b20dab216e17ce82b25bcd5 |

Observed pre-closeout aggregate CPU was 3.196403 seconds; active wall time was 3.570429 seconds. Conservative parent-plus-maximum-child peak RSS was 127,582,208 bytes. These are operational observations: CPU excludes final receipt/registry closeout, memory was observed rather than hard-contained, and no hard containment of an entire descendant process tree is claimed.

For local reproduction, use the commands in the README with an already-installed Python toolchain, a fresh environment and disabled package indexes/caches. The build is self-contained and has no runtime dependencies. This verified installation does not validate older Python versions or real-equipment use.
