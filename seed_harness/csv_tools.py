"""Small standard-library business tools, also runnable by standalone workers."""
import csv
import json
import math
from pathlib import Path
import sys


def absolute(path):
    value = Path(path)
    if not value.is_absolute():
        raise ValueError('absolute file path required')
    return value


def read_csv(input_path):
    with absolute(input_path).open(encoding='utf-8-sig', newline='') as source:
        rows = list(csv.DictReader(source))
    values = [float(row['value']) for row in rows]
    if not values or any(not math.isfinite(v) or v < 0 for v in values):
        raise ValueError('finite nonnegative values required')
    print('CSV読込完了: ' + str(len(values)) + '件')
    return {'values': values, 'reader_prefix': sys.prefix}


def aggregate(data, unit, output_path):
    if unit not in {'mm', 'cm'}:
        raise ValueError('explicit mm or cm unit required')
    values = data['values']
    if not values or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in values):
        raise ValueError('finite nonnegative values required')
    total = math.fsum(values) * (10 if unit == 'cm' else 1)
    if not math.isfinite(total):
        raise ValueError('total must be finite')
    result = {'total': total, 'unit': 'mm', 'count': len(values),
              'reader_prefix': data['reader_prefix'], 'aggregate_prefix': sys.prefix}
    # Exclusive output prevents silently repeating an external write.
    with absolute(output_path).open('x', encoding='utf-8') as target:
        json.dump(result, target, ensure_ascii=False, allow_nan=False)
    print('集計出力完了: ' + output_path)
    return dict(result, output_path=output_path)


def verify_csv(result, expected_total, expected_count):
    try:
        saved = json.loads(absolute(result['output_path']).read_text(encoding='utf-8'))
        passed = (saved['total'] == expected_total and saved['unit'] == 'mm'
                  and saved['count'] == expected_count
                  and saved['reader_prefix'] != saved['aggregate_prefix']
                  and all(saved[k] == result[k] for k in saved))
        return {'status': 'pass' if passed else 'fail', 'checks': ['values', 'unit', 'count', 'two_venvs', 'file_content']}
    except (OSError, ValueError, KeyError, TypeError):
        return {'status': 'unknown', 'checks': ['unreadable result']}


def verify_job(state, result):
    """Example verifier with fixed acceptance values, independent of the model."""
    return verify_csv(result, 60, 3)
