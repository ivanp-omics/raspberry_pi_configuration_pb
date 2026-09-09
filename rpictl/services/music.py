"""Glazba: pozadinska pjesma/mapa, pauzirana i nastavljena oko najava.

Ne zove AnnouncerService izravno - servisi se medusobno ne zovu. Umjesto
toga slusa postojeci EV_ANNOUNCE na busu (koji announcer vec objavljuje za
svaku najavu) i sam odlucuje treba li pauzirati/nastaviti glazbu. Time
stisavanje ne dira nijednu liniju u announcer.py.
"""

from __future__ import annotations

import logging

from ..bus import Bus
from ..clock import Clock
from ..hal.base import MusicPlayer
from ..models import EV_ANNOUNCE, EV_MUSIC

log = logging.getLogger(__name__)


class MusicService:
    name = "music"

    def __init__(self, clock: Clock, bus: Bus, music: MusicPlayer) -> None:
        self._clock = clock
        self._bus = bus
        self._music = music
        self._ducked = False

    async def play(self, track: str | None = None) -> None:
        await self._music.play(track)
        self._bus.publish(EV_MUSIC, {"state": "playing", "track": self._music.current_track})

    async def stop(self) -> None:
        await self._music.stop()
        self._bus.publish(EV_MUSIC, {"state": "stopped", "track": None})

    async def run(self) -> None:
        q = self._bus.subscribe()
        try:
            while True:
                msg = await q.get()
                if msg["type"] != EV_ANNOUNCE:
                    continue
                state = msg["data"]["state"]
                if state == "playing" and self._music.is_playing:
                    self._ducked = True
                    await self._music.pause()
                    self._bus.publish(
                        EV_MUSIC, {"state": "ducked", "track": self._music.current_track}
                    )
                elif state == "done" and self._ducked:
                    self._ducked = False
                    await self._music.resume()
                    self._bus.publish(
                        EV_MUSIC, {"state": "playing", "track": self._music.current_track}
                    )
        finally:
            self._bus.unsubscribe(q)

    def snapshot(self) -> dict:
        if self._ducked:
            status = "ducked"
        elif self._music.is_playing:
            status = "playing"
        else:
            status = "stopped"
        return {"status": status, "track": self._music.current_track}
