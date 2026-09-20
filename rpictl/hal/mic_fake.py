"""Lazni mikrofon - vraca sintetiziranu "tisu prostoriju".

Namjerno vraca stvarnu, svirljivu WAV datoteku, a ne prazne bajtove: tako se
cijeli put (ruta -> proxy -> player u browseru) moze isprobati bez hardvera.
Zvuk je slab sum s blagim brujanjem, da se odmah cuje kako je simuliran.

Zivotni ciklus je isti kao kod pravog snimaca (start/stop, granica trajanja),
inace se prekidac u sucelju ne bi mogao testirati u simulaciji.
"""

from __future__ import annotations

import io
import math
import random
import struct
import wave

from ..clock import Clock
from ..models import MicRecordError

RATE = 16000


class FakeMicRecorder:
    mime = "audio/wav"

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._started_at: float | None = None
        self._max_s = 0.0
        self.record_count = 0
        self.last_bytes = 0

    @property
    def recording(self) -> bool:
        return self._started_at is not None and self.elapsed_s < self._max_s

    @property
    def elapsed_s(self) -> float:
        if self._started_at is None:
            return 0.0
        # Skalirani sat: u simulaciji 60 s snimke prode za sekundu stvarnog
        # vremena, kao i sve ostalo u sustavu.
        return min(self._clock.now() - self._started_at, self._max_s)

    async def start(self, max_seconds: float) -> None:
        if self.recording:
            raise MicRecordError("snimanje je vec u tijeku")
        self._started_at = self._clock.now()
        self._max_s = max_seconds

    async def stop(self) -> bytes:
        if self._started_at is None:
            raise MicRecordError("slusanje nije bilo pokrenuto")
        trajanje = max(0.1, self.elapsed_s)
        self._started_at = None

        frames = bytearray()
        for i in range(int(trajanje * RATE)):
            t = i / RATE
            hum = 0.012 * math.sin(2.0 * math.pi * 50.0 * t)
            noise = random.uniform(-0.02, 0.02)
            frames += struct.pack("<h", int(max(-1.0, min(1.0, hum + noise)) * 32767))

        buf = io.BytesIO()
        with wave.open(buf, "wb") as fh:
            fh.setnchannels(1)
            fh.setsampwidth(2)
            fh.setframerate(RATE)
            fh.writeframes(bytes(frames))

        data = buf.getvalue()
        self.record_count += 1
        self.last_bytes = len(data)
        return data

    async def close(self) -> None:
        self._started_at = None
