#!/usr/bin/env python3
"""Append caller-observed CAL save timings after the save report; never update CAL."""
import sys
sys.dont_write_bytecode = True
import argparse
from datetime import datetime, timezone
import fcntl
import json
import math
from pathlib import Path
import re

DEFAULT_ROOT = Path('/Users/us/Tools/LocalData/Calendar_Local')
LOG_NAME = 'chat-save-timing.jsonl'


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('invalid_time')
    return value


def token(value, limit=128):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,' + str(limit) + '}', value):
        raise ValueError('invalid_label')
    return value


def project(value):
    allowed = {'clock', 'started_at_ms', 'saved_at_ms', 'route', 'operation',
               'request_id', 'receipt_id', 'calls'}
    if not isinstance(value, dict) or set(value) - allowed or value.get('clock') != 'caller_epoch_ms':
        raise ValueError('invalid_record')
    start, end = number(value['started_at_ms']), number(value['saved_at_ms'])
    if end < start:
        raise ValueError('clock_reversed')
    if value['route'] not in ('rdc', 'standard', 'mixed'):
        raise ValueError('invalid_route')
    calls, cursor = [], start
    for call in value.get('calls', []):
        if not isinstance(call, dict) or set(call) != {'phase', 'started_at_ms', 'received_at_ms'}:
            raise ValueError('invalid_call')
        a, b = number(call['started_at_ms']), number(call['received_at_ms'])
        if not cursor <= a <= b <= end:
            raise ValueError('call_out_of_order')
        calls.append(dict(phase=token(call['phase'], 64), started_at_ms=a,
                          received_at_ms=b, duration_ms=b-a))
        cursor = b
    elapsed = end - start
    call_ms = sum(c['duration_ms'] for c in calls)
    return dict(schema='cal-chat-save-timing-v1', clock='caller_epoch_ms',
                started_at_ms=start, saved_at_ms=end,
                started_at=datetime.fromtimestamp(start/1000, timezone.utc).isoformat(),
                saved_at=datetime.fromtimestamp(end/1000, timezone.utc).isoformat(),
                elapsed_ms=elapsed, calls=calls, call_wall_ms=call_ms,
                unclassified_ms=elapsed-call_ms, route=value['route'],
                operation=token(value['operation'], 64),
                request_id=token(value['request_id']), receipt_id=token(value['receipt_id']))


def record(value, local_root=DEFAULT_ROOT):
    row = project(value)
    root = Path(local_root).resolve()
    repository = Path(__file__).resolve().parents[1]
    if root == repository or repository in root.parents:
        raise ValueError('log_in_source_checkout')
    row['recorded_at'] = datetime.now(timezone.utc).isoformat()
    path = root / 'logs' / LOG_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as output:
        fcntl.flock(output, fcntl.LOCK_EX)
        output.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n')
        output.flush()
    return row


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--local-root', type=Path, default=DEFAULT_ROOT, help='synthetic tests only')
    args = p.parse_args(argv)
    try:
        row = record(json.load(sys.stdin), args.local_root)
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        print(json.dumps(dict(status='failed', reason='chat_timing_record_failed')))
        return 1
    print(json.dumps(dict(status='recorded', elapsed_ms=row['elapsed_ms'])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
