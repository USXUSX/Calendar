"""Optional post-commit signal. No display dependencies or formal-save retry."""
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime, timezone
from uuid import uuid4


def notify_committed(database, root):
    settings = Path(root) / 'settings'
    config = settings / 'change-notifier.json'
    if not config.exists():
        return
    identity = uuid4().hex
    result = dict(event_id=identity, committed=True, status='failed',
                  notified_at=datetime.now(timezone.utc).isoformat())
    try:
        value = json.loads(config.read_text())
        if Path(value['database']).resolve() != Path(database).resolve():
            return
        command = value['command']
        if not isinstance(command,list) or not command or not all(isinstance(a,str) and a for a in command):
            raise ValueError('invalid command')
        completed = subprocess.run(command, capture_output=True, text=True, timeout=15,
                                   env=dict(os.environ, CAL_COMMIT_ID=identity))
        # The consumer signals acceptance separately from its eventual publication.
        reply = json.loads(completed.stdout) if completed.stdout.strip() else {}
        result['status'] = 'accepted' if completed.returncode == 0 and reply.get('accepted') is True else 'failed'
    except Exception:
        pass  # The committed save/receipt remains authoritative.
    try:
        target = settings / 'change-notification-state.json'
        temporary = settings / ('.change-notification-' + identity)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd,'w') as handle:
            json.dump(result,handle)
        os.replace(temporary,target)
    except OSError:
        pass
