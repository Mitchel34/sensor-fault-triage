"""Small handcrafted checks; never call evaluate or run the frozen batch."""
import copy
import json
import math
import io
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout, redirect_stderr

from sensor_core import detect, fit, match, validate, SCENARIOS
from sensor_cli import parse, serialize, demo_rows, main


def rows(kind='trend', n=256):
    return [dict(timestamp=i, values={'sensor': (0 if kind == 'constant' else .001*i)
                 + (.2*math.sin(2*math.pi*i/64) if kind in ('periodic', 'noisy') else 0)
                 + (.001*((i*17)%11-5) if kind == 'noisy' else 0)}) for i in range(n)]


def event(family, start, end, detected=None, channel='sensor'):
    return dict(channel=channel, fault_type=family, start_index=start,
                end_index=end, detected_index=start if detected is None else detected)


class BehaviorTests(unittest.TestCase):
    def test_clean_controls(self):
        for kind in ('constant', 'trend', 'periodic', 'noisy'):
            with self.subTest(kind=kind):
                self.assertEqual(detect(rows(kind), 128), [])

    def test_missing_boundaries_and_terminal_time(self):
        data = rows()
        for i in (128, 150, 151, 255):
            data[i]['values']['sensor'] = None
        found = [e for e in detect(data, 128) if e['fault_type'] == 'missing']
        self.assertEqual([(e['start_index'], e['end_index'], e['detected_index']) for e in found],
                         [(128, 129, 128), (150, 152, 150), (255, 256, 255)])
        self.assertEqual(found[-1]['end_time'], 256)

    def test_stuck_full_run_and_eight_sample_threshold(self):
        data = rows()
        for i in range(150, 158):
            data[i]['values']['sensor'] = data[149]['values']['sensor']
        found = [e for e in detect(data, 128) if e['fault_type'] == 'stuck']
        self.assertEqual([(e['start_index'], e['end_index'], e['detected_index']) for e in found], [(149, 158, 156)])
        data = rows()
        for i in range(150, 157):
            data[i]['values']['sensor'] = .5
        self.assertFalse(any(e['fault_type'] == 'stuck' for e in detect(data, 128)))
        data[153]['values']['sensor'] = None
        self.assertFalse(any(e['fault_type'] == 'stuck' for e in detect(data, 128)))

    def test_spike_neighbors_and_delay(self):
        data = rows('constant')
        data[150]['values']['sensor'] = .081
        found = [e for e in detect(data, 128) if e['fault_type'] == 'spike']
        self.assertEqual([(e['start_index'], e['end_index'], e['detected_index']) for e in found], [(150, 151, 151)])
        data[150]['values']['sensor'] = .08
        self.assertEqual(detect(data, 128), [])
        data[150]['values']['sensor'] = 4
        data[149]['values']['sensor'] = None
        self.assertFalse(any(e['fault_type'] == 'spike' for e in detect(data, 128)))

    def test_spike_test_endpoints_not_eligible(self):
        data = rows('constant')
        data[128]['values']['sensor'] = .1
        data[-1]['values']['sensor'] = .1
        self.assertFalse(any(e['fault_type'] == 'spike' for e in detect(data, 128)))

    def test_drift_exact_evidence_boundaries(self):
        data = rows('constant')
        for i in range(160, 200):
            data[i]['values']['sensor'] = .64
        found = [e for e in detect(data, 128) if e['fault_type'] == 'drift']
        self.assertEqual([(e['start_index'], e['end_index'], e['detected_index']) for e in found], [(162, 229, 162)])
        data[180]['values']['sensor'] = None
        found = [e for e in detect(data, 128) if e['fault_type'] == 'drift']
        self.assertEqual([(e['start_index'], e['end_index']) for e in found], [(162, 180), (212, 229)])

    def test_calibration_isolation_and_determinism(self):
        data = rows('periodic')
        baseline = fit([r['values']['sensor'] for r in data[:128]])
        before = copy.deepcopy(data)
        for i in range(128, 256):
            data[i]['values']['sensor'] = None if i % 2 else 1e9
        self.assertEqual(fit([r['values']['sensor'] for r in data[:128]]), baseline)
        first = detect(data, 128)
        self.assertEqual(first, detect(copy.deepcopy(data), 128))
        self.assertEqual(serialize(first, 'json'), serialize(detect(data, 128), 'json'))
        self.assertEqual(before[:128], data[:128])

    def test_invalid_values(self):
        for value in (True, '1', float('nan'), float('inf'), -float('inf'), 10**400, 1e10):
            data = rows()
            data[-1]['values']['sensor'] = value
            with self.subTest(value=str(value)), self.assertRaises(ValueError):
                detect(data, 128)
        data = rows()
        data[0]['values']['sensor'] = None
        with self.assertRaises(ValueError):
            detect(data, 128)

    def test_invalid_timestamps(self):
        for value in (True, 1.5, None, -1, 1e10, float('inf'), 254, 257):
            data = rows()
            data[-1]['timestamp'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                detect(data, 128)

    def test_malformed_rows_and_calibration(self):
        for calibration in (True, 127, 256, 4097, 128.0):
            with self.assertRaises(ValueError):
                detect(rows(), calibration)
        for bad in ({}, {'timestamp': 255, 'values': {'other': 1}},
                    {'timestamp': 255, 'values': {'Bad': 1}},
                    {'timestamp': 255, 'values': {'sensor': 1}, 'extra': 1}):
            data = rows()
            data[-1] = bad
            with self.assertRaises(ValueError):
                detect(data, 128)
        with self.assertRaises(ValueError):
            detect(rows(n=128), 128)

    def test_zero_is_measurement(self):
        self.assertEqual(detect(rows('constant'), 128), [])
        self.assertEqual(parse('timestamp,sensor\n0,0\n1,\n', 'csv'),
                         [{'timestamp': 0, 'values': {'sensor': 0.0}}, {'timestamp': 1, 'values': {'sensor': None}}])

    def test_strict_parsers(self):
        for text in ('{"x":1,"x":2}', '[NaN]', '[Infinity]'):
            with self.assertRaises(ValueError):
                parse(text, 'json')
        for text in ('timestamp,sensor,sensor\n0,1,2', 'timestamp,sensor\n1.0,2',
                     'timestamp,sensor\n,2', 'timestamp,sensor\n0,NaN', 'timestamp,sensor\n0, 1'):
            with self.assertRaises(ValueError):
                parse(text, 'csv')
        data = rows()
        self.assertEqual(parse(json.dumps(data), 'json'), data)

    def test_match_one_to_one_ties_and_half_overlap(self):
        truth = [event('drift', 100, 120), event('drift', 110, 130)]
        predictions = [event('drift', 105, 125, 108)]
        pairs, extra, misses = match(predictions, truth)
        self.assertEqual(pairs[0][1]['start_index'], 100)
        self.assertEqual(len(misses), 1)
        self.assertEqual(extra, [])
        self.assertEqual(len(match([event('drift', 100, 110)], [truth[0]])[0]), 1)
        self.assertEqual(len(match([event('drift', 100, 109)], [truth[0]])[0]), 0)
        self.assertEqual(len(match([event('spike', 100, 120)], [truth[0]])[0]), 0)
        self.assertEqual(len(match([event('drift', 100, 120, channel='other')], [truth[0]])[0]), 0)

    def test_separate_demo(self):
        found = detect(demo_rows(), 128)
        self.assertEqual([(e['fault_type'], e['start_index'], e['end_index']) for e in found],
                         [('missing', 150, 155), ('spike', 170, 171)])
        self.assertTrue(serialize(found, 'csv').startswith('channel,fault_type,'))

    def test_frozen_scenario_enumeration(self):
        self.assertEqual(SCENARIOS, ('constant', 'trend', 'periodic', 'noisy', 'missing',
                                   'stuck', 'spike', 'drift', 'low', 'overlap'))

    def test_deep_json_bounded_cli_error(self):
        text = '['*2000+'0'+']'*2000
        out, err = io.StringIO(), io.StringIO()
        with patch('sys.stdin', io.StringIO(text)), redirect_stdout(out), redirect_stderr(err):
            status = main(['--calibration', '128'])
        self.assertEqual(status, 2)
        self.assertEqual(out.getvalue(), '')
        self.assertLess(len(err.getvalue()), 200)
        self.assertNotIn('Traceback', err.getvalue())
        self.assertIn('nesting', err.getvalue())

    def test_csv_quoting_main_boundary(self):
        prefix = 'timestamp,sensor\n'+''.join(str(i)+',0\n' for i in range(128))
        for suffix, expected in [('128,"0', 2), ('128,"0"0', 2), ('128,"0"', 0)]:
            out, err = io.StringIO(), io.StringIO()
            with patch('sys.stdin', io.StringIO(prefix+suffix)), redirect_stdout(out), redirect_stderr(err):
                status = main(['--input-format', 'csv', '--calibration', '128'])
            self.assertEqual(status, expected)
            if expected:
                self.assertEqual(out.getvalue(), '')
                self.assertLess(len(err.getvalue()), 200)
                self.assertNotIn('Traceback', err.getvalue())
            else:
                self.assertEqual(json.loads(out.getvalue()), [])

    def test_exact_eight_stuck_samples(self):
        data = rows()
        for i in range(150, 158):
            data[i]['values']['sensor'] = .5
        found = [e for e in detect(data, 128) if e['fault_type'] == 'stuck']
        self.assertEqual([(e['start_index'], e['end_index']) for e in found], [(150, 158)])


if __name__ == '__main__':
    unittest.main()
