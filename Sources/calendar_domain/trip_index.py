"""Opt-in, detached publication of the approved travel lookup index."""
import json
from pathlib import Path
import subprocess
import sys
import threading

CONFIG = 'trip-index-publisher.json'


def queue_publication(database, root):
    """Never wait for GitHub or affect a committed CAL result."""
    config = Path(root) / 'settings' / CONFIG
    try:
        if not config.is_file():
            return
        settings = json.loads(config.read_text(encoding='utf-8'))
        if Path(settings['database']).resolve() != Path(database).resolve():
            return
        script = Path(__file__).resolve().parents[2] / 'scripts' / 'publish_trip_index.py'
        worker = subprocess.Popen(
            [sys.executable, '-B', str(script), '--database', str(database), '--local-root', str(root)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True, close_fds=True)
        threading.Thread(target=worker.wait, daemon=True).start()
    except Exception:
        pass  # Formal commit/receipt remains authoritative.
