"""Uloziste. Tohle je to, co ze tri skriptu dela jeden nastroj.

Bez nej: UC1 nevi, co uz posilal; UC2 nema historii; UC3 zacina od nuly.
S nim: jeden SQLite soubor, ktery drzi eventy, alerty a vazby mezi nimi.

Commituje se do repa (je maly), takze GitHub Actions ma pameť mezi behy.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

from .models import Alert, Event

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  uid TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  url TEXT,
  source TEXT,
  date TEXT,
  city TEXT,
  organizer TEXT,
  description TEXT,
  price TEXT,
  topic TEXT,
  format TEXT,
  score INTEGER DEFAULT 0,
  score_breakdown TEXT,
  icp_id TEXT,
  summary TEXT,
  key_accounts TEXT,
  has_recon INTEGER DEFAULT 0,
  recon_file TEXT,
  first_seen TEXT,
  last_seen TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_date ON events(date);
CREATE INDEX IF NOT EXISTS idx_events_score ON events(score);

CREATE TABLE IF NOT EXISTS alerts (
  uid TEXT PRIMARY KEY,
  company TEXT NOT NULL,
  owner TEXT,
  event_uid TEXT,
  event_name TEXT,
  event_date TEXT,
  event_url TEXT,
  kind TEXT,
  detail TEXT,
  created_at TEXT,
  notified INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_alerts_company ON alerts(company);

CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  command TEXT,
  started_at TEXT,
  events_seen INTEGER DEFAULT 0,
  events_new INTEGER DEFAULT 0,
  alerts_new INTEGER DEFAULT 0
);
"""

LIST_FIELDS = {"key_accounts"}
JSON_FIELDS = {"score_breakdown"}


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.conn.commit()
        self.close()

    # ------------------------------------------------------ events
    def upsert_event(self, ev: Event) -> bool:
        """Vraci True, pokud je event novy (jeste jsme ho nevideli)."""
        now = datetime.now().isoformat(timespec="seconds")
        existing = self.conn.execute(
            "SELECT uid, first_seen, has_recon, recon_file FROM events WHERE uid=?", (ev.uid,)
        ).fetchone()
        is_new = existing is None

        ev.first_seen = existing["first_seen"] if existing else now
        ev.last_seen = now
        if existing and existing["has_recon"]:
            ev.has_recon = True
            ev.recon_file = existing["recon_file"]

        self.conn.execute(
            """INSERT INTO events
               (uid,name,url,source,date,city,organizer,description,price,topic,format,
                score,score_breakdown,icp_id,summary,key_accounts,has_recon,recon_file,
                first_seen,last_seen)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(uid) DO UPDATE SET
                 name=excluded.name, url=excluded.url, date=excluded.date,
                 city=excluded.city, organizer=excluded.organizer,
                 description=excluded.description, price=excluded.price,
                 topic=excluded.topic, format=excluded.format,
                 score=excluded.score, score_breakdown=excluded.score_breakdown,
                 icp_id=excluded.icp_id, summary=excluded.summary,
                 key_accounts=excluded.key_accounts, last_seen=excluded.last_seen""",
            (ev.uid, ev.name, ev.url, ev.source, ev.date, ev.city, ev.organizer,
             ev.description, ev.price, ev.topic, ev.format, ev.score,
             json.dumps(ev.score_breakdown), ev.icp_id, ev.summary,
             json.dumps(ev.key_accounts, ensure_ascii=False),
             int(ev.has_recon), ev.recon_file, ev.first_seen, ev.last_seen),
        )
        return is_new

    def mark_recon(self, event_uid: str, recon_file: str) -> None:
        self.conn.execute(
            "UPDATE events SET has_recon=1, recon_file=? WHERE uid=?", (recon_file, event_uid))
        self.conn.commit()

    def events(self, *, upcoming_only: bool = False, min_score: int = 0) -> list[Event]:
        sql = "SELECT * FROM events WHERE score >= ?"
        params: list = [min_score]
        if upcoming_only:
            sql += " AND (date IS NULL OR date >= ?)"
            params.append(date.today().isoformat())
        sql += " ORDER BY date IS NULL, date ASC, score DESC"
        return [_row_to_event(r) for r in self.conn.execute(sql, params)]

    def new_since(self, iso_ts: str) -> list[Event]:
        rows = self.conn.execute(
            "SELECT * FROM events WHERE first_seen >= ? ORDER BY score DESC", (iso_ts,))
        return [_row_to_event(r) for r in rows]

    def get_event(self, uid: str) -> Event | None:
        r = self.conn.execute("SELECT * FROM events WHERE uid=?", (uid,)).fetchone()
        return _row_to_event(r) if r else None

    def find_event_by_url(self, url: str) -> Event | None:
        probe = Event(name="", url=url)
        return self.get_event(probe.uid)

    # ------------------------------------------------------ alerts
    def add_alert(self, alert: Alert) -> bool:
        """Vraci True, pokud je alert novy. Diky tomu neposilame stejny 2x."""
        alert.created_at = alert.created_at or datetime.now().isoformat(timespec="seconds")
        cur = self.conn.execute(
            """INSERT OR IGNORE INTO alerts
               (uid,company,owner,event_uid,event_name,event_date,event_url,
                kind,detail,created_at,notified)
               VALUES (?,?,?,?,?,?,?,?,?,?,0)""",
            (alert.uid, alert.company, alert.owner, alert.event_uid, alert.event_name,
             alert.event_date, alert.event_url, alert.kind, alert.detail, alert.created_at),
        )
        return cur.rowcount > 0

    def unnotified_alerts(self) -> list[Alert]:
        rows = self.conn.execute(
            "SELECT * FROM alerts WHERE notified=0 ORDER BY event_date IS NULL, event_date")
        return [_row_to_alert(r) for r in rows]

    def all_alerts(self) -> list[Alert]:
        rows = self.conn.execute(
            "SELECT * FROM alerts ORDER BY event_date IS NULL, event_date DESC")
        return [_row_to_alert(r) for r in rows]

    def mark_notified(self, uids: list[str]) -> None:
        self.conn.executemany(
            "UPDATE alerts SET notified=1 WHERE uid=?", [(u,) for u in uids])
        self.conn.commit()

    # ------------------------------------------------------ runs
    def log_run(self, command: str, seen: int, new: int, alerts: int) -> None:
        self.conn.execute(
            "INSERT INTO runs (command,started_at,events_seen,events_new,alerts_new) "
            "VALUES (?,?,?,?,?)",
            (command, datetime.now().isoformat(timespec="seconds"), seen, new, alerts))
        self.conn.commit()

    def last_run(self, command: str) -> str | None:
        r = self.conn.execute(
            "SELECT started_at FROM runs WHERE command=? ORDER BY id DESC LIMIT 1",
            (command,)).fetchone()
        return r["started_at"] if r else None


def _row_to_event(r: sqlite3.Row) -> Event:
    ev = Event(
        name=r["name"], url=r["url"], source=r["source"], date=r["date"], city=r["city"],
        organizer=r["organizer"], description=r["description"], price=r["price"],
        topic=r["topic"], format=r["format"], score=r["score"] or 0,
        icp_id=r["icp_id"], summary=r["summary"],
        has_recon=bool(r["has_recon"]), recon_file=r["recon_file"],
        first_seen=r["first_seen"], last_seen=r["last_seen"],
    )
    ev.score_breakdown = json.loads(r["score_breakdown"] or "{}")
    ev.key_accounts = json.loads(r["key_accounts"] or "[]")
    return ev


def _row_to_alert(r: sqlite3.Row) -> Alert:
    return Alert(
        company=r["company"], owner=r["owner"], event_uid=r["event_uid"],
        event_name=r["event_name"], event_date=r["event_date"], event_url=r["event_url"],
        kind=r["kind"], detail=r["detail"], created_at=r["created_at"],
        notified=bool(r["notified"]),
    )
