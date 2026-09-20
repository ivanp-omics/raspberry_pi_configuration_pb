"""Alarm: prekidac, ne jednokratna najava.

Zasto zaseban servis, a ne stavka u AnnouncerService redu: red je za stvari
koje same zavrse, a alarm traje dok ga netko ne ugasi. Osim toga alarm DRZI
zvucni uredaj cijelo vrijeme, pa najave moraju cekati - to se izrazava kroz
`idle`, dogadaj koji AnnouncerService ceka prije svake reprodukcije.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from ..bus import Bus
from ..clock import Clock
from ..config import AlarmConfig
from ..hal.base import AudioPlayer
from ..models import EV_ANNOUNCE

log = logging.getLogger(__name__)


class AlarmService:
    name = "alarm"

    def __init__(self, cfg: AlarmConfig, clock: Clock, bus: Bus, audio: AudioPlayer) -> None:
        self._cfg = cfg
        self._clock = clock
        self._bus = bus
        self._audio = audio
        self._until: float | None = None
        self._timer: asyncio.Task | None = None
        # Postavljen = razglas je slobodan. AnnouncerService ovo ceka.
        self.idle = asyncio.Event()
        self.idle.set()

    @property
    def active(self) -> bool:
        return self._until is not None

    @property
    def remaining_s(self) -> float | None:
        if self._until is None:
            return None
        return max(0.0, self._until - self._clock.now())

    async def start(self) -> None:
        if self.active:
            return
        log.warning("ALARM ukljucen (%s, najvise %.0f s)", self._cfg.file, self._cfg.max_seconds)
        self.idle.clear()
        self._until = self._clock.now() + self._cfg.max_seconds

        # Prekini najavu koja svira - alarm ne ceka svoj red. Glazba se
        # pauzira preko EV_ANNOUNCE, isto kao kod obicne najave: MusicService
        # ne mora znati da alarm uopce postoji.
        await self._audio.stop()
        self._bus.publish(EV_ANNOUNCE, {"state": "playing", "id": "alarm", "text": None})
        await self._audio.start_loop(Path(self._cfg.file))

        self._timer = asyncio.create_task(self._auto_off())

    async def _auto_off(self) -> None:
        try:
            await self._clock.sleep(self._cfg.max_seconds)
        except asyncio.CancelledError:
            return
        log.warning("ALARM se gasi sam nakon %.0f s", self._cfg.max_seconds)
        await self.stop()

    async def stop(self) -> None:
        if not self.active:
            return
        timer, self._timer = self._timer, None
        self._until = None
        if timer is not None and timer is not asyncio.current_task():
            timer.cancel()
        await self._audio.stop_loop()
        self._bus.publish(EV_ANNOUNCE, {"state": "done", "id": "alarm"})
        self.idle.set()
        log.warning("ALARM iskljucen")

    def snapshot(self) -> dict:
        return {
            "active": self.active,
            "remaining_s": self.remaining_s,
            "max_seconds": self._cfg.max_seconds,
        }

    async def close(self) -> None:
        await self.stop()
