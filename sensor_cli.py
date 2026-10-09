"""JSON/CSV I/O for the offline detector. No equipment actions."""
import argparse
import csv
import io
import json
import re
import sys

from sensor_core import detect

FIELDS = ('channel', 'fault_type', 'start_index', 'end_index', 'start_time',
          'end_time', 'detected_index', 'score', 'explanation')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError('nonfinite JSON literal')


def parse(text, kind):
    if kind == 'json':
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
                    raise ValueError('excessive JSON nesting')
            elif char in ']}':
                depth -= 1
        try:
            return json.loads(text, object_pairs_hook=unique_object, parse_constant=reject_constant)
        except RecursionError:
            raise ValueError('excessive JSON nesting') from None
    reader = csv.reader(io.StringIO(text), strict=True)
    header = next(reader, None)
    if not header or header[0] != 'timestamp' or len(header) < 2 or len(set(header)) != len(header):
        raise ValueError('invalid CSV header')
    rows = []
    for fields in reader:
        if len(fields) != len(header) or re.fullmatch(r'0|[1-9][0-9]*', fields[0]) is None:
            raise ValueError('invalid CSV row')
        values = {}
        for name, value in zip(header[1:], fields[1:]):
            if value == '':
                values[name] = None
            elif re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?', value):
                values[name] = float(value)
            else:
                raise ValueError('invalid CSV measurement')
        rows.append(dict(timestamp=int(fields[0]), values=values))
    return rows


def serialize(events, kind):
    if kind == 'json':
        return json.dumps(events, sort_keys=True, allow_nan=False, indent=2)+'\n'
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator='\n')
    writer.writeheader()
    writer.writerows(events)
    return output.getvalue()


def demo_rows():
    """Separate handcrafted 192-row demo; not a batch evaluation trial."""
    rows = [dict(timestamp=i, values={'sensor': float(i)/1000}) for i in range(192)]
    for i in range(150, 155):
        rows[i]['values']['sensor'] = None
    rows[170]['values']['sensor'] += .1
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', nargs='?', help='input file; omit for stdin')
    parser.add_argument('--input-format', choices=('json', 'csv'), default='json')
    parser.add_argument('--output-format', choices=('json', 'csv'), default='json')
    parser.add_argument('--calibration', type=int)
    parser.add_argument('--demo', action='store_true', help='separate handcrafted demo, calibration=128')
    args = parser.parse_args(argv)
    if args.demo and (args.input is not None or args.calibration is not None):
        parser.error('--demo does not accept input or calibration')
    if not args.demo and args.calibration is None:
        parser.error('--calibration is required')
    try:
        if args.demo:
            rows, calibration = demo_rows(), 128
        else:
            if args.input:
                with open(args.input, encoding='utf-8', newline='') as handle:
                    text = handle.read()
            else:
                text = sys.stdin.read()
            rows, calibration = parse(text, args.input_format), args.calibration
        output = serialize(detect(rows, calibration), args.output_format)
    except (ValueError, TypeError, OverflowError, RecursionError, OSError, csv.Error) as exc:
        print('Invalid input: '+str(exc)[:160], file=sys.stderr)
        return 2
    sys.stdout.write(output)
    return 0


if __name__ == '__main__':
    sys.exit(main())
