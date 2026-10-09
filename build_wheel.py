"""Build the original dependency-free wheel using only the standard library."""
import argparse
import base64
import csv
import hashlib
import io
from pathlib import Path
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    info = 'sensor_fault_triage-0.1.0.dist-info/'
    files = {name: (root/name).read_bytes() for name in ('sensor_core.py', 'sensor_cli.py')}
    files[info+'METADATA'] = b'Metadata-Version: 2.1\nName: sensor-fault-triage\nVersion: 0.1.0\nSummary: Offline toy sensor fault diagnostics\nRequires-Python: >=3.10\n\n'
    files[info+'WHEEL'] = b'Wheel-Version: 1.0\nGenerator: original-stdlib-builder\nRoot-Is-Purelib: true\nTag: py3-none-any\n'
    files[info+'entry_points.txt'] = b'[console_scripts]\nsensor-fault-triage = sensor_cli:main\n'
    record = io.StringIO(newline='')
    writer = csv.writer(record, lineterminator='\n')
    for name, data in sorted(files.items()):
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode('ascii')
        writer.writerow((name, 'sha256='+digest, len(data)))
    writer.writerow((info+'RECORD', '', ''))
    files[info+'RECORD'] = record.getvalue().encode('utf-8')
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output/'sensor_fault_triage-0.1.0-py3-none-any.whl'
    with path.open('xb') as handle:
        with zipfile.ZipFile(handle, 'w', compression=zipfile.ZIP_STORED) as archive:
            for name, data in sorted(files.items()):
                entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                entry.external_attr = 0o100644 << 16
                archive.writestr(entry, data)
    print(path.name)


if __name__ == '__main__':
    main()
