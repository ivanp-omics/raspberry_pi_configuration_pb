"""Razglas: red cekanja s prioritetima.

Jedna najava odjednom. Alarm preskace red. Bez ovoga bi dvije najave
zasvirale jedna preko druge, sto na PA horni zvuci kao kvar.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
from pathlib import Path

from ..bus import Bus
from ..clock import Clock
from ..hal.base import AudioPlayer
from ..models import EV_ANNOUNCE, Announcement, Priority

log = logging.getLogger(__name__)


class AnnouncerService:
    name = "announcer"

    def __init__(self, clock: Clock, bus: Bus, audio: AudioPlayer) -> None:
        self._clock = clock
        self._bus = bus
        self._audio = audio
        # (prioritet, redni_broj) -> stabilan FIFO unutar istog prioriteta
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._seq = itertools.count()
        self._ids = itertools.count(1)
        self.current: Announcement | None = None
        self.done_count = 0

    def enqueue(
        self,
        text: str | None = None,
        path: str | None = None,
        priority: Priority = Priority.NORMAL,
    ) -> Announcement:
        if not text and not path:
            raise ValueError("najava mora imati tekst ili datoteku")
        ann = Announcement(
            id=f"a{next(self._ids)}", priority=priority, text=text, path=path
        )
        self._queue.put_nowait((int(priority), next(self._seq), ann))
        self._bus.publish(EV_ANNOUNCE, {"state": "queued", "id": ann.id, "text": text})
        return ann

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    async def run(self) -> None:
        while True:
            _, _, ann = await self._queue.get()
            self.current = ann
            self._bus.publish(EV_ANNOUNCE, {"state": "playing", "id": ann.id,
                                            "text": ann.text, "path": ann.path})
            try:
                if ann.path:
                    await self._audio.play_file(Path(ann.path))
                else:
                    await self._audio.say(ann.text or "")
                self.done_count += 1
            except Exception:  # noqa: BLE001
                log.exception("najava %s nije prosla", ann.id)
            finally:
                self.current = None
                self._bus.publish(EV_ANNOUNCE, {"state": "done", "id": ann.id})
                self._queue.task_done()

    def snapshot(self) -> dict:
        return {
            "playing": self.current.text or self.current.path if self.current else None,
            "pending": self.pending,
            "done": self.done_count,
        }
