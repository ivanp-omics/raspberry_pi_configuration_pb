"""Lazni razglas.

Ne pusta zvuk, ali stvarno ceka onoliko koliko bi najava trajala. Time se
testira ono sto je tesko: red cekanja, prioriteti i to da se dvije najave
ne preklapaju.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from ..clock import Clock

log = logging.getLogger(__name__)


class FakeAudioPlayer:
    def __init__(self, clock: Clock, speak_rate_wps: float = 2.5) -> None:
        self._clock = clock
        self._rate = speak_rate_wps
        self._task: asyncio.Task | None = None
        self._stopped = False
        self.now_playing: str | None = None
        self.play_count = 0

    async def _busy(self, label: str, seconds: float) -> None:
        self.now_playing = label
        self.play_count += 1
        log.info("razglas: %s (%.1f s)", label, seconds)
        # Cekanje ide kroz zaseban task da ga stop() moze prekinuti. Pravi
        # player ubije proces (AlsaAudioPlayer.stop), pa se lazni mora ponasati
        # isto - inace se prekid alarma ne moze testirati u simulaciji.
        self._stopped = False
        self._task = asyncio.create_task(self._clock.sleep(seconds))
        try:
            await self._task
        except asyncio.CancelledError:
            # Prekid preko stop() je uredan kraj najave - proguta se da ne
            # srusi petlju AnnouncerService-a. Ali ako otkaz dolazi izvana
            # (gasenje servisa), MORA se proslijediti dalje: progutan otkaz
            # znaci da se zadatak nikad ne ugasi i gasenje visi.
            if not self._stopped:
                raise
            log.info("razglas: %s prekinuto", label)
        finally:
            self._task = None
            self._stopped = False
            self.now_playing = None

    async def play_file(self, path: Path) -> None:
        await self._busy(f"datoteka {Path(path).name}", 4.0)

    async def say(self, text: str) -> None:
        words = max(1, len(text.split()))
        await self._busy(f'govor "{text[:40]}"', words / self._rate)

    async def stop(self) -> None:
        if self._task is not None and not self._task.done():
            self._stopped = True      # oznaka namjere - vidi _busy()
            self._task.cancel()
        self.now_playing = None

    async def close(self) -> None:
        await self.stop()
