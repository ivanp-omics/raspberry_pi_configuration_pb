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

    def __init__(
        self,
        clock: Clock,
        bus: Bus,
        audio: AudioPlayer,
        chime: str | None = None,
        gate: asyncio.Event | None = None,
    ) -> None:
        self._clock = clock
        self._bus = bus
        self._audio = audio
        self._chime = chime
        # Postavljen = razglas je slobodan. Alarm ga spusti dok svira, pa
        # najave cekaju umjesto da se bore za zvucni uredaj.
        self._gate = gate
        # (prioritet, redni_broj) -> stabilan FIFO unutar istog prioriteta
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._seq = itertools.count()
        self._ids = itertools.count(1)
        self.current: Announcement | None = None
        self.blocked = False
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

        # Alarm ne ceka. Prioritet ga inace stavlja na celo reda, ali red se
        # gleda tek kad trenutna najava zavrsi - a tridesetsekundna najava bi
        # tad drzala alarm zatvorenim. Zato se ono sto svira prekida odmah.
        if priority is Priority.ALARM and self.current is not None:
            log.warning("alarm %s prekida najavu %s", ann.id, self.current.id)
            try:
                asyncio.get_running_loop().create_task(self._audio.stop())
            except RuntimeError:
                # Nema petlje (izravan poziv izvan asyncia) - nema ni sto prekinuti.
                pass
        return ann

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    async def _cekaj_vrata(self) -> None:
        """Ceka da razglas bude slobodan (alarm ga drzi dok svira)."""
        if self._gate is None or self._gate.is_set():
            return
        # Bez ove oznake snapshot bi tvrdio da najava "svira" dok zapravo
        # stoji pred vratima - sucelje bi pisalo "Svira: ..." a nista se ne cuje.
        self.blocked = True
        try:
            await self._gate.wait()
        finally:
            self.blocked = False

    async def run(self) -> None:
        while True:
            _, _, ann = await self._queue.get()
            await self._cekaj_vrata()
            self.current = ann
            self._bus.publish(EV_ANNOUNCE, {"state": "playing", "id": ann.id,
                                            "text": ann.text, "path": ann.path})
            try:
                # Gong prije sadrzaja. Ne ide ispred samog gonga (da ne bude
                # dvostruk) ni ispred alarma (alarm ne ceka ceremoniju).
                if (
                    self._chime
                    and ann.path != self._chime
                    and ann.priority is not Priority.ALARM
                ):
                    await self._audio.play_file(Path(self._chime))

                # Opet vrata, ne samo na vrhu petlje: ako je alarm presjekao
                # gong, sadrzaj bi inace krenuo PREKO alarma i tukao se s njim
                # za zvucni uredaj. Ovako pricekamo da alarm zavrsi.
                await self._cekaj_vrata()

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
        svira = self.current.text or self.current.path if self.current else None
        return {
            # Dok ceka pred vratima najava nije "playing" - inace sucelje pise
            # da nesto svira, a razglas je zauzet alarmom.
            "playing": None if self.blocked else svira,
            "waiting": self.blocked,
            "pending": self.pending,
            "done": self.done_count,
        }
