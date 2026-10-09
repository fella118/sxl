"""Runtime state of the AI employee in SQLite: durable inbox, what the bot sent, pauses, counters, job runs.

The prospect list itself stays in CSV (it is the dataset Saad exports to Sheets); this is the service's memory.
"""
import datetime as dt
import os
import sqlite3
import threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS inbox   (id INTEGER PRIMARY KEY, contact_id TEXT NOT NULL, received_at TEXT NOT NULL,
                                    status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                                    result TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS inbox_status ON inbox(status, id);
CREATE TABLE IF NOT EXISTS handled (contact_id TEXT PRIMARY KEY, message_id TEXT NOT NULL, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sent    (id INTEGER PRIMARY KEY, contact_id TEXT NOT NULL, message_id TEXT NOT NULL,
                                    body TEXT NOT NULL, at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS sent_contact ON sent(contact_id);
CREATE TABLE IF NOT EXISTS paused  (contact_id TEXT PRIMARY KEY, reason TEXT NOT NULL, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS counters(day TEXT NOT NULL, key TEXT NOT NULL, n INTEGER NOT NULL, PRIMARY KEY(day, key));
CREATE TABLE IF NOT EXISTS jobs    (name TEXT PRIMARY KEY, run_key TEXT NOT NULL, at TEXT NOT NULL, ok INTEGER NOT NULL,
                                    error TEXT NOT NULL DEFAULT '');
"""
MAX_ATTEMPTS = 3


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


class Ops:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.executescript(SCHEMA)
            # a crash mid-processing: put those events back in the queue
            self.db.execute("UPDATE inbox SET status='pending' WHERE status='processing'")

    def _q(self, sql, *args):
        with self.lock:
            return self.db.execute(sql, args).fetchall()

    # --- inbox ----------------------------------------------------------------------------------------------
    def enqueue(self, contact_id):
        self._q("INSERT INTO inbox(contact_id, received_at) VALUES (?, ?)", contact_id, _now())

    def claim(self):
        """Next pending event, marked as processing. None when the inbox is empty."""
        with self.lock:
            row = self.db.execute("SELECT id, contact_id, attempts FROM inbox WHERE status='pending' "
                                  "ORDER BY id LIMIT 1").fetchone()
            if row:
                self.db.execute("UPDATE inbox SET status='processing', attempts=attempts+1 WHERE id=?", (row["id"],))
            return dict(row) if row else None

    def finish(self, event_id, result, ok=True):
        if ok:
            status = "done"
        else:
            attempts = self._q("SELECT attempts FROM inbox WHERE id=?", event_id)[0]["attempts"]
            status = "error" if attempts >= MAX_ATTEMPTS else "pending"
        self._q("UPDATE inbox SET status=?, result=? WHERE id=?", status, str(result)[:300], event_id)
        return status

    def pending(self):
        return self._q("SELECT COUNT(*) AS n FROM inbox WHERE status IN ('pending','processing')")[0]["n"]

    # --- conversations --------------------------------------------------------------------------------------
    def handled(self, contact_id):
        r = self._q("SELECT message_id FROM handled WHERE contact_id=?", contact_id)
        return r[0]["message_id"] if r else None

    def set_handled(self, contact_id, message_id):
        self._q("INSERT INTO handled VALUES (?, ?, ?) ON CONFLICT(contact_id) DO UPDATE SET message_id=excluded.message_id, "
                "at=excluded.at", contact_id, message_id, _now())

    def record_sent(self, contact_id, message_id, body):
        self._q("INSERT INTO sent(contact_id, message_id, body, at) VALUES (?, ?, ?, ?)",
                contact_id, message_id or "", body, _now())

    def ours(self, contact_id):
        """(message ids, bodies) the bot sent in this conversation."""
        rows = self._q("SELECT message_id, body FROM sent WHERE contact_id=?", contact_id)
        return {r["message_id"] for r in rows if r["message_id"]}, {r["body"].strip() for r in rows}

    def pause(self, contact_id, reason):
        self._q("INSERT OR REPLACE INTO paused VALUES (?, ?, ?)", contact_id, reason, _now())

    def paused(self, contact_id):
        r = self._q("SELECT reason FROM paused WHERE contact_id=?", contact_id)
        return r[0]["reason"] if r else None

    def unpause(self, contact_id):
        self._q("DELETE FROM paused WHERE contact_id=?", contact_id)

    # --- counters and jobs ----------------------------------------------------------------------------------
    def bump(self, day, key, by=1):
        self._q("INSERT INTO counters VALUES (?, ?, ?) ON CONFLICT(day, key) DO UPDATE SET n=n+excluded.n", day, key, by)

    def count(self, day, key):
        r = self._q("SELECT n FROM counters WHERE day=? AND key=?", day, key)
        return r[0]["n"] if r else 0

    def job_key(self, name):
        r = self._q("SELECT run_key FROM jobs WHERE name=?", name)
        return r[0]["run_key"] if r else None

    def record_job(self, name, run_key, ok, error=""):
        self._q("INSERT OR REPLACE INTO jobs VALUES (?, ?, ?, ?, ?)", name, run_key, _now(), int(ok), error[:500])

    def jobs(self):
        return {r["name"]: {"at": r["at"], "ok": bool(r["ok"]), "error": r["error"]}
                for r in self._q("SELECT * FROM jobs")}

    def close(self):
        with self.lock:
            self.db.close()

    def backup(self, dest):
        """Consistent copy of the database while it is in use."""
        with self.lock:
            target = sqlite3.connect(dest)
            self.db.backup(target)
            target.close()
