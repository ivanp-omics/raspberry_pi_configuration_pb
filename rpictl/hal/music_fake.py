"""Lazna glazba.

Ne pusta zvuk, samo drzi stanje. Za razliku od FakeAudioPlayer (najave,
poznato trajanje), glazba traje dok je netko ne zaustavi - nema se sto
cekati na Clock.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class FakeMusicPlayer:
    def __init__(self, volume: int = 40) -> None:
        self._playing = False
        self._track: str | None = None
        self._paused_at: str | None = None
        self._volume = volume

    @property
    def is_playing(self) -> bool:
        return self._playing

    @property
    def current_track(self) -> str | None:
        return self._track

    @property
    def volume(self) -> int:
        return self._volume

    async def set_volume(self, level: int) -> None:
        self._volume = max(0, min(100, int(level)))
        log.info("glazba: glasnoca %d %%", self._volume)

    async def play(self, track: str | None = None) -> None:
        self._track = track or "(mapa media/music, izmijesano)"
        self._playing = True
        self._paused_at = None
        log.info("glazba: svira %s", self._track)

    async def pause(self) -> None:
        if not self._playing:
            return
        self._paused_at = self._track
        self._playing = False
        log.info("glazba: pauzirana (%s)", self._paused_at)

    async def resume(self) -> None:
        if self._paused_at is None:
            return
        self._track = self._paused_at
        self._playing = True
        self._paused_at = None
        log.info("glazba: nastavlja (%s)", self._track)

    async def stop(self) -> None:
        self._playing = False
        self._track = None
        self._paused_at = None

    async def close(self) -> None:
        await self.stop()
