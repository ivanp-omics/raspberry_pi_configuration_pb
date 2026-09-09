"""Zapis mjerenja u SQLite.

Pretplacuje se na bus, ne zove nikoga. sqlite3 je blokirajuci pa svaki
upis ide u thread.

VAZNO za Pi s read-only overlayem: db_path mora pokazivati na zapisivi
mount (zasebna particija ili USB). Na overlayu baza prezivi do prvog
reboota i onda nestane bez ijedne greske u logu.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path

from ..bus import Bus
from ..clock import Clock
from ..config import TelemetryConfig
from ..models import EV_FAN, EV_READING

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    ts REAL PRIMARY KEY,
    temperature_c REAL NOT NULL,
    humidity_pct REAL,
    pressure_hpa REAL,
    gas_ohms REAL
);
CREATE TABLE IF NOT EXISTS fan_events (
    ts REAL PRIMARY KEY,
    on_state INTEGER NOT NULL,
    reason TEXT,
    healthy INTEGER
);
CREATE INDEX IF NOT EXISTS ix_readings_ts ON readings(ts);
"""


class TelemetryService:
    name = "telemetry"

    def __init__(self, cfg: TelemetryConfig, clock: Clock, bus: Bus) -> None:
        self.cfg = cfg
        self._clock = clock
        self._bus = bus
        self._db: sqlite3.Connection | None = None
        self.rows_written = 0

    def _connect(self) -> sqlite3.Connection:
        p = Path(self.cfg.db_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(p, check_same_thread=False)
        db.executescript(_SCHEMA)
        db.commit()
        return db

    async def start(self) -> None:
        self._db = await asyncio.to_thread(self._connect)
        log.info("telemetrija: %s", Path(self.cfg.db_path).resolve())

    def _insert_reading(self, d: dict) -> None:
        assert self._db is not None
        self._db.execute(
            "INSERT OR REPLACE INTO readings VALUES (?,?,?,?,?)",
            (d["ts"], d["temperature_c"], d.get("humidity_pct"),
             d.get("pressure_hpa"), d.get("gas_ohms")),
        )
        self._db.commit()

    def _insert_fan(self, d: dict) -> None:
        assert self._db is not None
        self._db.execute(
            "INSERT OR REPLACE INTO fan_events VALUES (?,?,?,?)",
            (d["ts"], int(d["on"]), d.get("reason"), int(d.get("healthy", True))),
        )
        self._db.commit()

    def _history(self, hours: float, limit: int) -> list[dict]:
        assert self._db is not None
        since = self._clock.now() - hours * 3600.0
        cur = self._db.execute(
            "SELECT ts, temperature_c, humidity_pct FROM readings "
            "WHERE ts >= ? ORDER BY ts",
            (since,),
        )
        rows = cur.fetchall()
        if len(rows) > limit:  # prorijedi da graf ostane brz
            step = len(rows) // limit + 1
            rows = rows[::step]
        return [{"ts": r[0], "temperature_c": r[1], "humidity_pct": r[2]} for r in rows]

    async def history(self, hours: float = 24.0, limit: int = 500) -> list[dict]:
        if self._db is None:
            return []
        return await asyncio.to_thread(self._history, hours, limit)

    def _purge(self) -> int:
        assert self._db is not None
        cutoff = self._clock.now() - self.cfg.retention_days * 86400.0
        cur = self._db.execute("DELETE FROM readings WHERE ts < ?", (cutoff,))
        self._db.execute("DELETE FROM fan_events WHERE ts < ?", (cutoff,))
        self._db.commit()
        return cur.rowcount

    async def run(self) -> None:
        q = self._bus.subscribe()
        purge_every = 3600.0
        next_purge = self._clock.now() + purge_every
        try:
            while True:
                msg = await q.get()
                try:
                    if msg["type"] == EV_READING:
                        await asyncio.to_thread(self._insert_reading, msg["data"])
                        self.rows_written += 1
                    elif msg["type"] == EV_FAN:
                        await asyncio.to_thread(self._insert_fan, msg["data"])
                except sqlite3.Error:
                    log.exception("upis u bazu nije uspio")

                if self._clock.now() >= next_purge:
                    next_purge = self._clock.now() + purge_every
                    deleted = await asyncio.to_thread(self._purge)
                    if deleted:
                        log.info("obrisano %d starih zapisa", deleted)
        finally:
            self._bus.unsubscribe(q)

    async def close(self) -> None:
        if self._db is not None:
            await asyncio.to_thread(self._db.close)
            self._db = None

    def snapshot(self) -> dict:
        return {"rows_written": self.rows_written, "db": self.cfg.db_path}
