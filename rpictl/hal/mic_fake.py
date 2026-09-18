"""Lazni mikrofon - vraca sintetiziranu "tisu prostoriju".

Namjerno vraca stvarnu, svirljivu WAV datoteku, a ne prazne bajtove: tako se
cijeli put (ruta -> proxy -> player u browseru) moze isprobati bez hardvera.
Zvuk je slab sum s blagim brujanjem, da se odmah cuje kako je simuliran.
"""

from __future__ import annotations

import io
import math
import random
import struct
import wave

from ..clock import Clock

RATE = 16000


class FakeMicRecorder:
    mime = "audio/wav"

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self.record_count = 0
        self.last_bytes = 0

    async def record(self, seconds: float) -> bytes:
        # Ceka stvarno (skaliranim) vremenom, kao i pravi snimac. Bez ovoga
        # simulacija vraca deset sekundi zvuka trenutno, pa se nikad ne
        # provjeri ni stanje "snimam..." u sucelju ni zaklucavanje mikrofona.
        await self._clock.sleep(seconds)

        frames = int(seconds * RATE)
        samples = bytearray()
        for i in range(frames):
            t = i / RATE
            hum = 0.012 * math.sin(2.0 * math.pi * 50.0 * t)
            noise = random.uniform(-0.02, 0.02)
            samples += struct.pack("<h", int(max(-1.0, min(1.0, hum + noise)) * 32767))

        buf = io.BytesIO()
        with wave.open(buf, "wb") as fh:
            fh.setnchannels(1)
            fh.setsampwidth(2)
            fh.setframerate(RATE)
            fh.writeframes(bytes(samples))

        data = buf.getvalue()
        self.record_count += 1
        self.last_bytes = len(data)
        return data

    async def close(self) -> None:
        return None
