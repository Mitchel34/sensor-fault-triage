"""Original toy-sensor detector and admitted in-memory evaluation; protocol v2."""
import math
import random
import statistics
import time

FAMILIES = ('missing', 'stuck', 'spike', 'drift')
SCENARIOS = ('constant', 'trend', 'periodic', 'noisy', 'missing', 'stuck',
             'spike', 'drift', 'low', 'overlap')


def finite(value):
    return type(value) in (int, float) and abs(value) <= 1e9 and math.isfinite(value)


def validate(rows, calibration):
    if type(rows) is not list or not 129 <= len(rows) <= 100000:
        raise ValueError('row count must be 129..100000')
    if type(calibration) is not int or not 128 <= calibration <= 4096 or calibration >= len(rows):
        raise ValueError('invalid calibration length')
    channels = None
    timestamps = []
    for i, row in enumerate(rows):
        if type(row) is not dict or set(row) != {'timestamp', 'values'}:
            raise ValueError('malformed row')
        t = row['timestamp']
        if type(t) is not int or not 0 <= t <= 10**9:
            raise ValueError('invalid timestamp')
        values = row['values']
        if type(values) is not dict or not 1 <= len(values) <= 16:
            raise ValueError('invalid channel map')
        for name in values:
            if (type(name) is not str or not 1 <= len(name) <= 32
                    or name[0] not in 'abcdefghijklmnopqrstuvwxyz'
                    or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789_' for c in name)):
                raise ValueError('invalid channel name')
        if channels is None:
            channels = sorted(values)
        if sorted(values) != channels:
            raise ValueError('channel set changed')
        for value in values.values():
            if value is None:
                if i < calibration:
                    raise ValueError('missing calibration sample')
            elif not finite(value):
                raise ValueError('invalid measurement')
        timestamps.append(t)
    step = timestamps[1] - timestamps[0]
    if step <= 0 or any(timestamps[i] - timestamps[i-1] != step for i in range(1, len(rows))):
        raise ValueError('timestamps must be increasing and uniform')
    return channels, timestamps, step


def fit(samples):
    """Fit only an explicitly supplied calibration vector."""
    if type(samples) is not list or not 128 <= len(samples) <= 4096 or not all(finite(v) for v in samples):
        raise ValueError('invalid calibration samples')
    slope = statistics.median((samples[i]-samples[i-64])/64 for i in range(64, len(samples)))
    intercept = statistics.median(v-slope*i for i, v in enumerate(samples))
    residual = [v-(intercept+slope*i) for i, v in enumerate(samples)]
    center = statistics.median(residual)
    scale = max(.01, 1.4826*statistics.median(abs(v-center) for v in residual))
    dynamic = max(samples)-min(samples)
    if not all(math.isfinite(v) for v in (slope, intercept, scale, dynamic)):
        raise ValueError('nonfinite calibration arithmetic')
    return intercept, slope, scale, dynamic


def detect(rows, calibration):
    channels, timestamps, step = validate(rows, calibration)
    events = []
    n = len(rows)
    for channel in channels:
        y = [row['values'][channel] for row in rows]
        a, b, s, dynamic = fit(y[:calibration])
        residual = [None if v is None else v-(a+b*i) for i, v in enumerate(y)]
        if any(v is not None and not math.isfinite(v) for v in residual):
            raise ValueError('nonfinite residual arithmetic')

        def emit(family, start, end, detected, score):
            if not math.isfinite(score) or score < 0:
                raise ValueError('nonfinite score arithmetic')
            wording = {'missing': 'Explicit missing run; length',
                       'stuck': 'Exact repeated values; length divided by 8',
                       'spike': 'Neighbor midpoint deviation divided by 8 calibration scales',
                       'drift': 'Maximum trailing mean residual divided by 4 calibration scales'}
            events.append(dict(channel=channel, fault_type=family, start_index=start,
                               end_index=end, start_time=timestamps[start],
                               end_time=timestamps[end] if end < n else timestamps[-1]+step,
                               detected_index=detected, score=float(score),
                               explanation=wording[family]+': '+format(score, '.6f')))

        i = calibration
        while i < n:
            if y[i] is None:
                end = i+1
                while end < n and y[end] is None:
                    end += 1
                emit('missing', i, end, i, end-i)
                i = end
            else:
                i += 1
        i = calibration
        while i < n:
            end = i+1
            if y[i] is not None:
                while end < n and y[end] == y[i]:
                    end += 1
                if dynamic > 1e-8 and end-i >= 8:
                    emit('stuck', i, end, i+7, (end-i)/8)
            i = end
        for i in range(calibration+1, n-1):
            if any(y[k] is None for k in (i-1, i, i+1)):
                continue
            deviation = abs(y[i]-(y[i-1]+y[i+1])/2)
            if deviation > 8*s and abs(y[i+1]-y[i-1]) <= 2*s:
                emit('spike', i, i+1, i+1, deviation/(8*s))
        start = None
        peak = 0.0
        for i in range(calibration, n):
            active = False
            score = 0.0
            if i >= calibration+31:
                window = residual[i-31:i+1]
                if all(v is not None for v in window):
                    score = abs(sum(window)/32)/(4*s)
                    if not math.isfinite(score):
                        raise ValueError('nonfinite drift arithmetic')
                    active = score > 1
            if active:
                if start is None:
                    start = i
                peak = max(peak, score)
            elif start is not None:
                emit('drift', start, i, start, peak)
                start, peak = None, 0.0
        if start is not None:
            emit('drift', start, n, start, peak)
    return sorted(events, key=lambda e: (e['channel'], e['start_index'], e['end_index'], e['fault_type']))


def generate(seed, scenario):
    """One frozen stream and its logical labels; no I/O or fitted parameters."""
    if type(seed) is not int or seed not in range(20) or type(scenario) is not int or scenario not in range(10):
        raise ValueError('invalid frozen trial')
    columns = []
    truth = []
    for j in range(4):
        rng = random.Random(seed*1000+scenario*10+j)
        trend = 0 if scenario == 0 else .0005
        amp = 0 if scenario < 2 else .2
        sigma = 0 if scenario < 3 else .02
        y = [10+2*j+trend*t+amp*math.sin(2*math.pi*t/64+j*math.pi/4)+rng.gauss(0, sigma)
             for t in range(2048)]
        labels = []
        if scenario == 4:
            y[900:932] = [None]*32
            labels = [('missing', 900, 932)]
        elif scenario == 5:
            y[1000:1064] = [y[999]]*64
            labels = [('stuck', 1000, 1064)]
        elif scenario == 6:
            y[1100] += 4
            labels = [('spike', 1100, 1101)]
        elif scenario == 7:
            for t in range(1200, 1360):
                y[t] += 3
            labels = [('drift', 1200, 1360)]
        elif scenario == 8:
            y[800] = None
            y[900:904] = [y[899]]*4
            y[1050] += .15
            for t in range(1200, 1360):
                y[t] += .15
            labels = [('missing', 800, 801), ('stuck', 900, 904),
                      ('spike', 1050, 1051), ('drift', 1200, 1360)]
        elif scenario == 9:
            for t in range(1000, 1200):
                y[t] += 3
            y[1050:1114] = [y[1049]]*64
            y[1080] += 4
            y[1090:1106] = [None]*16
            labels = [('drift', 1000, 1200), ('stuck', 1050, 1114),
                      ('spike', 1080, 1081), ('missing', 1090, 1106)]
        truth.extend(dict(channel='c'+str(j), fault_type=f, start_index=start, end_index=end)
                     for f, start, end in labels)
        columns.append(y)
    rows = [dict(timestamp=t, values={'c'+str(j): columns[j][t] for j in range(4)}) for t in range(2048)]
    return rows, truth


def match(predictions, truth):
    """Deterministic per-channel/family greedy IoU matching; one trial only."""
    key = lambda e: (e['channel'], e['start_index'], e['end_index'], e['fault_type'])
    p, q = sorted(predictions, key=key), sorted(truth, key=key)
    candidates = []
    for qi, target in enumerate(q):
        for pi, event in enumerate(p):
            if (event['channel'], event['fault_type']) != (target['channel'], target['fault_type']):
                continue
            lo = max(event['start_index'], target['start_index'])
            hi = min(event['end_index'], target['end_index'])
            union = max(event['end_index'], target['end_index'])-min(event['start_index'], target['start_index'])
            overlap = max(0, hi-lo)
            if overlap and overlap/union >= .5:
                candidates.append((-overlap/union, abs(event['start_index']-target['start_index']),
                                   target['start_index'], target['end_index'], event['start_index'],
                                   event['end_index'], qi, pi))
    used_q, used_p, pairs = set(), set(), []
    for candidate in sorted(candidates):
        qi, pi = candidate[-2:]
        if qi not in used_q and pi not in used_p:
            used_q.add(qi)
            used_p.add(pi)
            pairs.append((p[pi], q[qi]))
    return pairs, [e for i, e in enumerate(p) if i not in used_p], [e for i, e in enumerate(q) if i not in used_q]


def evaluate():
    """Execute ONLY through the admitted once-only production runner."""
    cpu, wall = time.process_time(), time.perf_counter()
    m = {}
    for group in ('clear', 'low', 'overlap'):
        for family in FAMILIES:
            for stat in ('tp', 'fp', 'fn', 'delay_sum', 'delay_n'):
                m[group+'_'+family+'_'+stat] = 0
    for control in SCENARIOS[:4]:
        for stat in ('events', 'observations', 'per_1000'):
            m['clean_'+control+'_'+stat] = 0
    for stat in ('streams', 'channel_streams', 'observations', 'test_observations', 'clean_streams',
                 'clear_streams', 'low_streams', 'overlap_streams', 'clear_truth', 'low_truth', 'overlap_truth'):
        m[stat] = 0
    seen_seeds, seen_channels, seen_lengths, seen_calibrations = set(), set(), set(), set()
    for seed in range(20):
        for scenario in range(10):
            rows, truth = generate(seed, scenario)
            predictions = detect(rows, 512)
            count_channels = len(rows[0]['values'])
            seen_seeds.add(seed)
            seen_channels.update(rows[0]['values'])
            seen_lengths.add(len(rows))
            seen_calibrations.add(512)
            m['streams'] += 1
            m['channel_streams'] += count_channels
            m['observations'] += len(rows)*count_channels
            observations = (len(rows)-512)*count_channels
            m['test_observations'] += observations
            if scenario < 4:
                prefix = 'clean_'+SCENARIOS[scenario]
                m['clean_streams'] += 1
                m[prefix+'_events'] += len(predictions)
                m[prefix+'_observations'] += observations
            else:
                group = 'clear' if scenario < 8 else SCENARIOS[scenario]
                m[group+'_streams'] += 1
                m[group+'_truth'] += len(truth)
                pairs, extras, misses = match(predictions, truth)
                for prediction, target in pairs:
                    prefix = group+'_'+target['fault_type']
                    m[prefix+'_tp'] += 1
                    m[prefix+'_delay_n'] += 1
                    m[prefix+'_delay_sum'] += max(0, prediction['detected_index']-target['start_index'])
                for event in extras:
                    m[group+'_'+event['fault_type']+'_fp'] += 1
                for target in misses:
                    m[group+'_'+target['fault_type']+'_fn'] += 1
    for family in FAMILIES:
        prefix = 'clear_'+family
        tp, fp, fn = (m[prefix+'_'+stat] for stat in ('tp', 'fp', 'fn'))
        m[prefix+'_precision'] = tp/(tp+fp) if tp+fp else 1.0
        m[prefix+'_recall'] = tp/(tp+fn) if tp+fn else 1.0
    for control in SCENARIOS[:4]:
        prefix = 'clean_'+control
        m[prefix+'_per_1000'] = 1000*m[prefix+'_events']/m[prefix+'_observations']
    m.update(seeds=len(seen_seeds), channels=len(seen_channels), timestamps=max(seen_lengths),
             calibration_samples=max(seen_calibrations), evaluation_cpu_seconds=time.process_time()-cpu,
             evaluation_wall_seconds=time.perf_counter()-wall)
    checks = [('streams_complete', m['streams'] == 200),
              ('channel_streams_complete', m['channel_streams'] == 800),
              ('observations_complete', m['observations'] == 1638400),
              ('test_observations_complete', m['test_observations'] == 1228800),
              ('clean_streams_complete', m['clean_streams'] == 80),
              ('clear_streams_complete', m['clear_streams'] == 80),
              ('stress_streams_complete', m['low_streams'] == 20 and m['overlap_streams'] == 20),
              ('truth_complete', m['clear_truth'] == 320 and m['low_truth'] == 320 and m['overlap_truth'] == 320),
              ('metric_count_complete', len(m) == 97)]
    return dict(metrics=m, checks=[dict(name=name, passed=bool(passed)) for name, passed in checks])
