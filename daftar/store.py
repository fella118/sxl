"""SQLite storage: clients, the monthly document checklist, conversations, follow-ups."""

import json
import sqlite3
from datetime import date
from pathlib import Path

DOC_TYPES = ["releve_bancaire", "factures_achats", "factures_ventes", "etat_paie"]
DOC_LABELS = {
    "releve_bancaire": "Relevé bancaire",
    "factures_achats": "Factures d'achats",
    "factures_ventes": "Factures de ventes",
    "etat_paie": "État de paie",
}
# missing -> partial -> received ; not_applicable when the client confirms there is nothing to send
CHECK_STATUSES = ["missing", "partial", "received", "not_applicable"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS clients (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    contact TEXT NOT NULL,
    phone TEXT NOT NULL,
    language TEXT NOT NULL,            -- darija | francais
    expected_docs TEXT NOT NULL        -- JSON list of DOC_TYPES
);
CREATE TABLE IF NOT EXISTS checklist (
    client_code TEXT NOT NULL,
    period TEXT NOT NULL,              -- YYYY-MM the documents belong to
    doc_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'missing',
    note TEXT NOT NULL DEFAULT '',
    updated_on TEXT,
    PRIMARY KEY (client_code, period, doc_type)
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_code TEXT NOT NULL,
    day TEXT NOT NULL,
    direction TEXT NOT NULL,           -- in | out
    kind TEXT NOT NULL,                -- text | template | file
    body TEXT NOT NULL,
    file_id INTEGER,
    period TEXT                        -- set on template reminders, to count nudges per period
);
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_code TEXT NOT NULL,
    period TEXT NOT NULL,
    name TEXT NOT NULL,
    mime TEXT NOT NULL,
    path TEXT NOT NULL,
    doc_type TEXT
);
CREATE TABLE IF NOT EXISTS followups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_code TEXT NOT NULL,
    due TEXT NOT NULL,
    reason TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS flags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_code TEXT NOT NULL,
    day TEXT NOT NULL,
    reason TEXT NOT NULL,
    resolved INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_code TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cache_read_tokens INTEGER NOT NULL,
    cache_write_tokens INTEGER NOT NULL,
    cost_usd REAL NOT NULL
);
"""


class Store:
    def __init__(self, path: str | Path = ":memory:"):
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    # --- settings -------------------------------------------------------
    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self.db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.db.commit()

    @property
    def today(self) -> date:
        return date.fromisoformat(self.get_setting("today", date.today().isoformat()))

    @today.setter
    def today(self, value: date) -> None:
        self.set_setting("today", value.isoformat())

    # --- clients & checklist -------------------------------------------
    def add_client(self, code, name, contact, phone, language, expected_docs) -> None:
        unknown = set(expected_docs) - set(DOC_TYPES)
        if unknown:
            raise ValueError(f"unknown doc types: {sorted(unknown)}")
        self.db.execute(
            "INSERT OR REPLACE INTO clients VALUES (?, ?, ?, ?, ?, ?)",
            (code, name, contact, phone, language, json.dumps(expected_docs)),
        )
        self.db.commit()

    def clients(self) -> list[dict]:
        rows = self.db.execute("SELECT * FROM clients ORDER BY name").fetchall()
        return [self._client(r) for r in rows]

    def client(self, code: str) -> dict:
        row = self.db.execute("SELECT * FROM clients WHERE code = ?", (code,)).fetchone()
        if row is None:
            raise KeyError(f"unknown client {code}")
        return self._client(row)

    @staticmethod
    def _client(row) -> dict:
        c = dict(row)
        c["expected_docs"] = json.loads(c["expected_docs"])
        return c

    def open_period(self, code: str, period: str) -> None:
        for doc_type in self.client(code)["expected_docs"]:
            self.db.execute(
                "INSERT OR IGNORE INTO checklist (client_code, period, doc_type) VALUES (?, ?, ?)",
                (code, period, doc_type),
            )
        self.db.commit()

    def checklist(self, code: str, period: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT doc_type, status, note, updated_on FROM checklist "
            "WHERE client_code = ? AND period = ?",
            (code, period),
        ).fetchall()
        order = {d: i for i, d in enumerate(DOC_TYPES)}
        return sorted((dict(r) for r in rows), key=lambda r: order[r["doc_type"]])

    def outstanding(self, code: str, period: str) -> list[str]:
        return [r["doc_type"] for r in self.checklist(code, period) if r["status"] in ("missing", "partial")]

    def update_checklist(self, code: str, period: str, doc_type: str, status: str, note: str) -> None:
        if status not in CHECK_STATUSES:
            raise ValueError(f"bad status {status}")
        cur = self.db.execute(
            "UPDATE checklist SET status = ?, note = ?, updated_on = ? "
            "WHERE client_code = ? AND period = ? AND doc_type = ?",
            (status, note, self.today.isoformat(), code, period, doc_type),
        )
        if cur.rowcount == 0:
            raise KeyError(f"{doc_type} is not expected from {code} for {period}")
        self.db.commit()

    # --- messages & files ----------------------------------------------
    def add_message(self, code, direction, kind, body, file_id=None, period=None) -> int:
        cur = self.db.execute(
            "INSERT INTO messages (client_code, day, direction, kind, body, file_id, period) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (code, self.today.isoformat(), direction, kind, body, file_id, period),
        )
        self.db.commit()
        return cur.lastrowid

    def messages(self, code: str, limit: int = 200) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM (SELECT * FROM messages WHERE client_code = ? ORDER BY id DESC LIMIT ?) ORDER BY id",
            (code, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def add_file(self, code, period, name, mime, path) -> int:
        cur = self.db.execute(
            "INSERT INTO files (client_code, period, name, mime, path) VALUES (?, ?, ?, ?, ?)",
            (code, period, name, mime, str(path)),
        )
        self.db.commit()
        return cur.lastrowid

    def file(self, file_id: int) -> dict | None:
        row = self.db.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        return dict(row) if row else None

    def files(self, code: str, period: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM files WHERE client_code = ? AND period = ? ORDER BY id", (code, period)
        ).fetchall()
        return [dict(r) for r in rows]

    def tag_file(self, file_id: int, code: str, doc_type: str) -> None:
        cur = self.db.execute(
            "UPDATE files SET doc_type = ? WHERE id = ? AND client_code = ?", (doc_type, file_id, code)
        )
        if cur.rowcount == 0:
            raise KeyError(f"file {file_id} does not belong to {code}")
        self.db.commit()

    # --- follow-ups & flags --------------------------------------------
    def schedule_followup(self, code: str, due: date, reason: str) -> None:
        # One pending follow-up per client: a new promise replaces the old schedule.
        self.db.execute("UPDATE followups SET done = 1 WHERE client_code = ? AND done = 0", (code,))
        self.db.execute(
            "INSERT INTO followups (client_code, due, reason) VALUES (?, ?, ?)",
            (code, due.isoformat(), reason),
        )
        self.db.commit()

    def pending_followup(self, code: str) -> dict | None:
        row = self.db.execute(
            "SELECT * FROM followups WHERE client_code = ? AND done = 0", (code,)
        ).fetchone()
        return dict(row) if row else None

    def close_followups(self, code: str) -> None:
        self.db.execute("UPDATE followups SET done = 1 WHERE client_code = ? AND done = 0", (code,))
        self.db.commit()

    def add_flag(self, code: str, reason: str) -> None:
        self.db.execute(
            "INSERT INTO flags (client_code, day, reason) VALUES (?, ?, ?)",
            (code, self.today.isoformat(), reason),
        )
        self.db.commit()

    def flags(self, code: str | None = None) -> list[dict]:
        sql, args = "SELECT * FROM flags WHERE resolved = 0", ()
        if code:
            sql, args = sql + " AND client_code = ?", (code,)
        return [dict(r) for r in self.db.execute(sql + " ORDER BY id", args).fetchall()]

    def resolve_flag(self, flag_id: int) -> None:
        self.db.execute("UPDATE flags SET resolved = 1 WHERE id = ?", (flag_id,))
        self.db.commit()

    # --- usage -----------------------------------------------------------
    def record_usage(self, code, input_tokens, output_tokens, cache_read, cache_write, cost_usd) -> None:
        self.db.execute(
            "INSERT INTO usage (client_code, input_tokens, output_tokens, cache_read_tokens, "
            "cache_write_tokens, cost_usd) VALUES (?, ?, ?, ?, ?, ?)",
            (code, input_tokens, output_tokens, cache_read, cache_write, cost_usd),
        )
        self.db.commit()

    def total_cost_usd(self) -> float:
        return self.db.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM usage").fetchone()[0]

    def nudges_sent(self, code: str, period: str) -> int:
        return self.db.execute(
            "SELECT COUNT(*) FROM messages WHERE client_code = ? AND kind = 'template' AND period = ?",
            (code, period),
        ).fetchone()[0]
