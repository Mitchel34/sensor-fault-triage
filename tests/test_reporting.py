"""Invented exporter schema fixtures only; these are not project measurements."""
import copy
import io
import json
import tempfile
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
import unittest
from export_results import summarize, FAMILIES, MEMORY_DESCRIPTION, main, strict_receipt, MAX_RECEIPT_BYTES


def invented_receipt():
    m = {}
    for group in ('clear', 'low', 'overlap'):
        for family in FAMILIES:
            for stat, value in (('tp', 0), ('fp', 0), ('fn', 80), ('delay_sum', 0), ('delay_n', 0)):
                m[group+'_'+family+'_'+stat] = value
    for family in FAMILIES:
        m['clear_'+family+'_precision'] = 1.0
        m['clear_'+family+'_recall'] = 0.0
    for control in ('constant', 'trend', 'periodic', 'noisy'):
        for stat, value in (('events', 0), ('observations', 122880), ('per_1000', 0.0)):
            m['clean_'+control+'_'+stat] = value
    m.update(streams=200, channel_streams=800, observations=1638400, test_observations=1228800,
             clean_streams=80, clear_streams=80, low_streams=20, overlap_streams=20,
             clear_truth=320, low_truth=320, overlap_truth=320, seeds=20, channels=4,
             timestamps=2048, calibration_samples=512, evaluation_cpu_seconds=0.0, evaluation_wall_seconds=0.0)
    names = ('streams_complete', 'channel_streams_complete', 'observations_complete',
             'test_observations_complete', 'clean_streams_complete', 'clear_streams_complete',
             'stress_streams_complete', 'truth_complete', 'metric_count_complete')
    return {'outcome': 'pass', 'result': {'metrics': m, 'checks': [{'name': n, 'passed': True} for n in names]},
            'cpu_seconds': .25, 'worker_cpu_seconds': .2, 'supervisor_cpu_seconds': .05,
            'wall_seconds': .3, 'peak_memory_bytes': 1000000,
            'cpu_limit_seconds': 60, 'wall_limit_seconds': 120, 'memory_limit_bytes': 268435456,
            'memory_measurement': MEMORY_DESCRIPTION}


class ReportingTests(unittest.TestCase):
    def test_scientific_failure_retains_metrics(self):
        receipt = invented_receipt()
        original = copy.deepcopy(receipt)
        report = summarize(receipt)
        self.assertEqual(report['scientific_outcome'], 'fail')
        self.assertEqual(len(report['scientific_checks']), 11)
        self.assertEqual(len(report['metrics']), 97)
        self.assertEqual(report['metrics'], original['result']['metrics'])
        self.assertEqual(receipt, original)
        self.assertTrue(all(row['mean_delay_samples'] is None for row in report['event_summary']))
        self.assertTrue(all(row['missed'] == 80 for row in report['event_summary']))

    def test_integrity_failure_is_distinct(self):
        receipt = invented_receipt()
        receipt['result']['checks'][0]['passed'] = False
        with self.assertRaises(ValueError):
            summarize(receipt)
        with self.assertRaises(ValueError):
            summarize({'outcome': 'fail', 'result': None})

    def test_recomputed_science_rejects_forged_precision(self):
        receipt = invented_receipt()
        receipt['result']['metrics']['clear_missing_precision'] = .9
        with self.assertRaises(ValueError):
            summarize(receipt)

    def test_metric_and_coverage_corruption(self):
        for name, value in (('streams', 199), ('evaluation_cpu_seconds', float('nan')),
                            ('low_missing_fn', 79), ('clean_noisy_per_1000', 1)):
            receipt = invented_receipt()
            receipt['result']['metrics'][name] = value
            with self.subTest(name=name), self.assertRaises(ValueError):
                summarize(receipt)

    def test_required_sanitized_resources(self):
        receipt = invented_receipt()
        report = summarize(receipt)
        expected = {k: v for k, v in receipt.items() if k not in ('outcome', 'result')}
        self.assertEqual(report['resources'], expected)
        for key in expected:
            absent = invented_receipt()
            del absent[key]
            with self.subTest(missing=key), self.assertRaises(ValueError):
                summarize(absent)
            for value in (True, 'PRIVATE_SENTINEL', {'text': 'PRIVATE_SENTINEL'}, [], -1,
                          float('nan'), float('inf'), 10**400):
                corrupt = invented_receipt()
                corrupt[key] = value
                with self.subTest(key=key, type=type(value).__name__), self.assertRaises(ValueError):
                    summarize(corrupt)
        for key in ('peak_memory_bytes', 'memory_limit_bytes'):
            receipt = invented_receipt()
            receipt[key] = 1.5
            with self.assertRaises(ValueError):
                summarize(receipt)
        for key in ('cpu_limit_seconds', 'wall_limit_seconds', 'memory_limit_bytes'):
            receipt = invented_receipt()
            receipt[key] = 0
            with self.assertRaises(ValueError):
                summarize(receipt)

    def test_exact_boolean_check_contract(self):
        for value in (1, 1.0, False, 'true', None):
            receipt = invented_receipt()
            receipt['result']['checks'][0]['passed'] = value
            with self.assertRaises(ValueError):
                summarize(receipt)
        for mode in ('missing', 'extra', 'duplicate', 'reorder', 'missing_key'):
            receipt = invented_receipt()
            checks = receipt['result']['checks']
            if mode == 'missing': checks.pop()
            elif mode == 'extra': checks[0]['extra'] = 1
            elif mode == 'duplicate': checks[1] = dict(checks[0])
            elif mode == 'reorder': checks[0], checks[1] = checks[1], checks[0]
            else: del checks[0]['name']
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                summarize(receipt)

    def assert_cli_rejects(self, raw):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, destination = root/'invented.json', root/'output'
            source.write_bytes(raw)
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                status = main([str(source), str(destination)])
            self.assertEqual(status, 2)
            self.assertEqual(out.getvalue(), '')
            self.assertLess(len(err.getvalue()), 100)
            self.assertNotIn('Traceback', err.getvalue())
            self.assertNotIn('PRIVATE_SENTINEL', err.getvalue())
            self.assertFalse(destination.exists())

    def test_malformed_receipt_cli_has_no_output_effects(self):
        for raw in (b'{"outcome":"pass","outcome":"fail"}', b'{"unused":NaN}',
                    b'{"unused":Infinity}', b'[]', b'null', b'"PRIVATE_SENTINEL"',
                    b'{bad', b'\xff', b'['*2000+b'0'+b']'*2000,
                    b' '* (MAX_RECEIPT_BYTES+1)):
            self.assert_cli_rejects(raw)
        for target in ('metric', 'resource'):
            receipt = invented_receipt()
            if target == 'metric': receipt['result']['metrics']['evaluation_cpu_seconds'] = 10**400
            else: receipt['cpu_seconds'] = 10**400
            self.assert_cli_rejects(json.dumps(receipt).encode())
        receipt = invented_receipt()
        receipt['memory_measurement'] = 'PRIVATE_SENTINEL'
        self.assert_cli_rejects(json.dumps(receipt).encode())
        with self.assertRaises(ValueError):
            summarize([])

    def test_scientific_thresholds_and_adverse_results_preserved(self):
        receipt = invented_receipt()
        m = receipt['result']['metrics']
        for family in FAMILIES:
            p = 'clear_'+family
            m.update({p+'_tp': 64, p+'_fp': 16, p+'_fn': 16, p+'_delay_n': 64,
                      p+'_delay_sum': 128, p+'_precision': .8, p+'_recall': .8})
        m['clean_noisy_events'] = 5
        m['clean_noisy_per_1000'] = 5000/122880
        report = summarize(receipt)
        self.assertEqual(report['scientific_outcome'], 'pass')
        self.assertEqual(report['metrics']['clean_noisy_events'], 5)
        self.assertEqual(report['metrics']['low_missing_fn'], 80)
        m['clear_missing_fp'] = 17
        m['clear_missing_precision'] = 64/81
        self.assertEqual(summarize(receipt)['scientific_outcome'], 'fail')
        m['clear_missing_fp'], m['clear_missing_precision'] = 16, .8
        m['clean_constant_events'] = 1
        m['clean_constant_per_1000'] = 1000/122880
        self.assertFalse(summarize(receipt)['scientific_checks'][8]['passed'])

    def test_scientific_miss_export_and_existing_output_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, destination = root/'invented.json', root/'output'
            source.write_text(json.dumps(invented_receipt()))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main([str(source), str(destination)]), 0)
            raw = (destination/'results.json').read_bytes()
            report = json.loads(raw)
            self.assertEqual(report['scientific_outcome'], 'fail')
            self.assertEqual(len(report['metrics']), 97)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main([str(source), str(destination)]), 2)
            self.assertEqual((destination/'results.json').read_bytes(), raw)


if __name__ == '__main__':
    unittest.main()
