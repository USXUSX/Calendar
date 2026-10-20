"""Explicit #250 metadata migration. Run after SQLite backup; never infer people."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from Sources.calendar_domain import CalendarDomain
from Sources.calendar_domain.trip_lifecycle import lodging_nights
from Sources.calendar_domain.travel import validate_metadata


def migrate(database, local_root):
    cal = CalendarDomain(database, local_root)
    changes = []
    for travel in cal.list_travel():
        with cal._read() as c:
            row = cal._travel_row(c, travel['id'])
            data = json.loads(row['data_json'])
        trip = cal.get_effective_trip(travel['id']) if travel['has_itinerary'] else None
        if 'nights' not in data:
            nights = trip.get('nights') if trip else None
            if trip and nights is None:
                # Only complete overnight coverage supplies a confirmed count.
                from datetime import date, timedelta
                start = date.fromisoformat(trip['dateRange']['start'])
                end = date.fromisoformat(trip['dateRange']['end'])
                covered = {d['date'] for d in trip['days'] if any(
                    (i['category'] == 'accommodation' and not any(w in i['action'].casefold() for w in ('チェックアウト','checkout','check-out','check out')))
                    or '機内泊' in i['action'] for i in d['scheduleItems'])}
                required = {(start + timedelta(days=n)).isoformat() for n in range((end-start).days)}
                if required <= covered: nights = lodging_nights(trip)
            data['nights'] = nights
        data.setdefault('participants', trip.get('participants', []) if trip else [])
        validate_metadata(data)
        changes.append((json.dumps(data, ensure_ascii=False), travel['id']))
    with sqlite3.connect(database) as c:
        for payload, tid in changes:
            previous = c.execute('SELECT data_json FROM travel_basics WHERE trip_id=?', (tid,)).fetchone()[0]
            if json.loads(previous) != json.loads(payload):
                c.execute('UPDATE travel_basics SET data_json=? WHERE trip_id=?', (payload, tid))
                c.execute('UPDATE trips SET version=version+1 WHERE id=?', (tid,))
    return len(changes)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('database', type=Path); p.add_argument('local_root', type=Path)
    a = p.parse_args()
    print('checked_travels=' + str(migrate(a.database, a.local_root)))
