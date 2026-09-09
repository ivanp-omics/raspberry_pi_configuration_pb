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
        self.now_playing: str | None = None
        self.play_count = 0

    async def _busy(self, label: str, seconds: float) -> None:
        self.now_playing = label
        self.play_count += 1
        log.info("razglas: %s (%.1f s)", label, seconds)
        try:
            await self._clock.sleep(seconds)
        finally:
            self.now_playing = None

    async def play_file(self, path: Path) -> None:
        await self._busy(f"datoteka {Path(path).name}", 4.0)

    async def say(self, text: str) -> None:
        words = max(1, len(text.split()))
        await self._busy(f'govor "{text[:40]}"', words / self._rate)

    async def stop(self) -> None:
        self.now_playing = None

    async def close(self) -> None:
        await self.stop()
