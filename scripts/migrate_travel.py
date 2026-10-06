"""Explicit additive Calendar #221 migration; no implicit runtime migration."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.init_calendar_db import extend_travel
from Sources.calendar_domain import CalendarDomain


def migrate(database, local_root):
    cal=CalendarDomain(database,local_root)
    summaries=cal.list_trips()
    c=sqlite3.connect(Path(database).resolve().as_uri()+'?mode=rw',uri=True)
    try:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT version FROM schema_meta').fetchone()!=(3,): raise ValueError('CAL v3 required')
        extend_travel(c)
        for trip in summaries:
            data=dict(title=trip['title'],start_date=trip['dateRange']['start'],end_date=trip['dateRange']['end'],date_status='confirmed',transport='other')
            c.execute('INSERT OR IGNORE INTO travel_basics VALUES (?,?,1)',(trip['trip_id'],json.dumps(data,ensure_ascii=False)))
        c.commit()
    finally: c.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('database',type=Path);p.add_argument('local_root',type=Path)
    a=p.parse_args();migrate(a.database,a.local_root)
