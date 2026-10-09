"""Export metrics from a genuine admitted receipt; never import the detector."""
import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

FAMILIES = ('missing', 'stuck', 'spike', 'drift')
MAX_RECEIPT_BYTES = 1048576
MEMORY_DESCRIPTION = 'sum_of_process_high_water_marks_conservative_not_simultaneous_rss'


def number(value):
    # Bound before float conversion so arbitrarily large JSON integers fail safely.
    return type(value) in (int, float) and 0 <= value <= 10**12 and math.isfinite(value)


def strict_receipt(raw):
    if len(raw) > MAX_RECEIPT_BYTES:
        raise ValueError('receipt exceeds size bound')
    text = raw.decode('utf-8') if isinstance(raw, bytes) else raw
    depth, quoted, escaped = 0, False, False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in '[{':
            depth += 1
            if depth > 64:
                raise ValueError('excessive receipt nesting')
        elif char in ']}':
            depth -= 1

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate receipt key')
            result[key] = value
        return result

    def constant(value):
        raise ValueError('nonstandard receipt number')

    try:
        result = json.loads(text, object_pairs_hook=unique, parse_constant=constant)
    except (RecursionError, OverflowError):
        raise ValueError('excessive receipt nesting or number') from None
    if type(result) is not dict:
        raise ValueError('receipt must be an object')
    return result


def validate_resources(receipt):
    numeric = ('cpu_seconds', 'peak_memory_bytes', 'wall_seconds', 'worker_cpu_seconds',
               'supervisor_cpu_seconds', 'cpu_limit_seconds', 'memory_limit_bytes', 'wall_limit_seconds')
    resources = {}
    for key in numeric:
        value = receipt.get(key)
        if not number(value):
            raise ValueError('missing or invalid resource measurement')
        if key.endswith('_bytes') and type(value) is not int:
            raise ValueError('resource bytes must be integers')
        if '_limit_' in key and value <= 0:
            raise ValueError('resource limits must be positive')
        resources[key] = value
    if receipt.get('memory_measurement') != MEMORY_DESCRIPTION:
        raise ValueError('unsupported memory measurement description')
    resources['memory_measurement'] = MEMORY_DESCRIPTION
    return resources


def summarize(receipt):
    if type(receipt) is not dict or receipt.get('outcome') != 'pass' or type(receipt.get('result')) is not dict:
        raise ValueError('successful execution receipt with retained results required')
    result = receipt['result']
    checks = result.get('checks')
    expected = ('streams_complete', 'channel_streams_complete', 'observations_complete',
                'test_observations_complete', 'clean_streams_complete', 'clear_streams_complete',
                'stress_streams_complete', 'truth_complete', 'metric_count_complete')
    if (not isinstance(checks, list) or len(checks) != 9
            or any(type(c) is not dict or set(c) != {'name', 'passed'} or c['name'] != name
                   or c['passed'] is not True for c, name in zip(checks, expected))):
        raise ValueError('execution integrity checks incomplete')
    m = result.get('metrics')
    if type(m) is not dict or len(m) != 97 or any(not number(v) for v in m.values()):
        raise ValueError('invalid metric schema')
    expected_keys = set()
    for group in ('clear', 'low', 'overlap'):
        for family in FAMILIES:
            expected_keys.update(group+'_'+family+'_'+s for s in ('tp', 'fp', 'fn', 'delay_sum', 'delay_n'))
    for family in FAMILIES:
        expected_keys.update('clear_'+family+'_'+s for s in ('precision', 'recall'))
    for control in ('constant', 'trend', 'periodic', 'noisy'):
        expected_keys.update('clean_'+control+'_'+s for s in ('events', 'observations', 'per_1000'))
    coverage = dict(streams=200, channel_streams=800, observations=1638400,
                    test_observations=1228800, clean_streams=80, clear_streams=80,
                    low_streams=20, overlap_streams=20, clear_truth=320, low_truth=320,
                    overlap_truth=320, seeds=20, channels=4, timestamps=2048, calibration_samples=512)
    expected_keys.update(coverage)
    expected_keys.update(('evaluation_cpu_seconds', 'evaluation_wall_seconds'))
    if set(m) != expected_keys or any(type(m[k]) is not int or m[k] != v for k, v in coverage.items()):
        raise ValueError('inconsistent coverage or metric keys')
    for control in ('constant', 'trend', 'periodic', 'noisy'):
        prefix = 'clean_'+control
        if (type(m[prefix+'_events']) is not int or m[prefix+'_observations'] != 122880
                or m[prefix+'_per_1000'] != 1000*m[prefix+'_events']/122880):
            raise ValueError('inconsistent clean counters')
    scientific = []
    table = []
    for group in ('clear', 'low', 'overlap'):
        for family in FAMILIES:
            prefix = group+'_'+family
            tp, fp, fn, delay_sum, delay_n = (m[prefix+'_'+s] for s in ('tp', 'fp', 'fn', 'delay_sum', 'delay_n'))
            if any(type(v) is not int for v in (tp, fp, fn, delay_sum, delay_n)) or delay_n != tp or tp+fn != 80:
                raise ValueError('inconsistent event counters')
            precision = tp/(tp+fp) if tp+fp else 1.0
            recall = tp/(tp+fn) if tp+fn else 1.0
            if group == 'clear':
                if m[prefix+'_precision'] != precision or m[prefix+'_recall'] != recall:
                    raise ValueError('inconsistent scientific metrics')
                scientific.extend([dict(name=prefix+'_precision_target', passed=precision >= .8),
                                   dict(name=prefix+'_recall_target', passed=recall >= .8)])
            table.append(dict(group=group, family=family, tp=tp, fp=fp, fn=fn,
                              precision=precision, recall=recall, delay_matches=delay_n,
                              missed=fn, mean_delay_samples=delay_sum/delay_n if delay_n else None))
    for control in ('constant', 'trend', 'periodic'):
        scientific.append(dict(name='clean_'+control+'_zero_events', passed=m['clean_'+control+'_events'] == 0))
    resources = validate_resources(receipt)
    return dict(metrics=m, event_summary=table, scientific_checks=scientific,
                scientific_outcome='pass' if all(c['passed'] for c in scientific) else 'fail',
                resources=resources,
                resource_note='Runner fields preserve their recorded scope; process peak memory is operational, not hard containment. Evaluator timing excludes supervisor and closeout. No real-equipment validation.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args(argv)
    try:
        with args.receipt.open('rb') as handle:
            raw = handle.read(MAX_RECEIPT_BYTES+1)
        report = summarize(strict_receipt(raw))
        encoded = json.dumps(report, indent=2, sort_keys=True, allow_nan=False)+'\n'
        # A fresh directory preserves every earlier successful or failed report.
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output/'results.json').write_text(encoded, encoding='utf-8')
        with (args.output/'events-summary.csv').open('x', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(report['event_summary'][0]))
            writer.writeheader()
            writer.writerows(report['event_summary'])
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, OSError, csv.Error):
        print('Invalid receipt or output destination; no valid export completed.', file=sys.stderr)
        return 2
    print(json.dumps({'scientific_outcome': report['scientific_outcome'],
                      'receipt_sha256': hashlib.sha256(raw).hexdigest()}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
