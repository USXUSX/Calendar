"""Opt-in, invocation-local diagnostics. Never include domain values or exception text."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
import json
import os
import time
from uuid import uuid4

_current = ContextVar('cal_timing', default=None)


def _clock():
    try:
        return time.monotonic_ns()
    except Exception:
        return None


def _elapsed(start):
    end = _clock()
    return None if start is None or end is None else max(0, (end-start)/1_000_000)


class Timing:
    def __init__(self, operation, group=None):
        self.started = _clock()
        self.record = dict(protocol='cal-timing-v1', diagnostic_id=uuid4().hex,
                           group_id=group, operation=operation, spans=[], counts={})

    @contextmanager
    def activate(self):
        token = _current.set(self)
        try:
            yield self
        finally:
            _current.reset(token)

    def finish(self, result, code):
        # Fixed vocabulary only: never copy reason, IDs, payloads or receipts.
        status = result.get('status')
        self.record['status'] = status if status in ('ok', 'ready', 'committed', 'rejected', 'unknown', 'not_found') else 'other'
        resolution = result.get('resolution')
        self.record['resolution'] = resolution if resolution in ('new', 'replayed') else None
        self.record['failure_class'] = {0: None, 2: 'validation', 3: 'conflict', 4: 'not_found', 5: 'unknown'}.get(code, 'interrupted')
        self.record['exit_code'] = code
        self.record['total_ms'] = _elapsed(self.started)

    def emit(self, stream, path=None):
        try:
            line = json.dumps(self.record, sort_keys=True)+'\n'
        except Exception:
            return
        try:
            stream.write(line)
            stream.flush()
        except Exception:
            pass
        if path is not None:
            try:
                target = Path(path).resolve()
                if any((parent/'.git').exists() for parent in target.parents):
                    return
                fd = os.open(target, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
                with os.fdopen(fd, 'w') as handle:
                    handle.write(line)
            except Exception:
                pass  # Diagnostics must never change a save result.


@contextmanager
def span(name):
    timing = _current.get()
    if timing is None:
        yield
        return
    start = _clock()
    status = 'ok'
    try:
        yield
    except BaseException:
        status = 'error'
        raise
    finally:
        try:
            timing.record['spans'].append(dict(stage=name, ms=_elapsed(start), status=status))
        except Exception:
            pass


def stage(name):
    def decorate(method):
        @wraps(method)
        def wrapped(*args, **kwargs):
            with span(name):
                return method(*args, **kwargs)
        return wrapped
    return decorate


def count(**values):
    timing = _current.get()
    if timing is not None:
        try:
            timing.record['counts'].update({key: value for key, value in values.items() if type(value) is int})
        except Exception:
            pass


class CommitTiming:
    """Preserve sqlite connection context semantics, timing its commit/rollback only."""
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection.__enter__()

    def __exit__(self, *exc):
        with span('db_commit' if exc[0] is None else 'db_rollback'):
            return self.connection.__exit__(*exc)


def count_trip(trip):
    if _current.get() is None or not isinstance(trip, dict):
        return
    try:
        values = {key: len(trip[key]) for key in ('places', 'transports', 'days') if isinstance(trip.get(key), list)}
        values['schedule_items'] = sum(len(day['scheduleItems']) for day in trip.get('days', [])
                                       if isinstance(day, dict) and isinstance(day.get('scheduleItems'), list))
        count(**values)
    except Exception:
        pass
