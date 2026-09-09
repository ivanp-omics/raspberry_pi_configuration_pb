"""Sat kao ovisnost, a ne kao globalna funkcija.

Zasto: termostat mjeri "minimalno vrijeme rada" i "zastarjelo ocitanje".
Ako pozove time.time() izravno, test tih pravila traje sate. Ovako se
vrijeme ubrizgava - u produkciji stvarno, u simulaciji ubrzano, u testovima
rucno pomicano.
"""

from __future__ import annotations

import asyncio
import time
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def now(self) -> float:
        """Sekunde. Monotono rastuce, usporedivo sa samim sobom."""
        ...

    async def sleep(self, seconds: float) -> None:
        """Ceka zadani broj sekundi *u vremenu ovog sata*."""
        ...


class RealClock:
    """Stvarno vrijeme. Ovo ide na Pi."""

    def now(self) -> float:
        return time.time()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class ScaledClock:
    """Ubrzano vrijeme za desktop simulaciju.

    speed=60 znaci: sleep(60) se vrati nakon 1 stvarne sekunde, a now()
    je u meduvremenu skocio za 60. Cijeli sustav - termostat, senzor,
    telemetrija - zivi u istom ubrzanom vremenu, pa je ponasanje isto
    kao u stvarnom, samo brze.
    """

    def __init__(self, speed: float = 60.0) -> None:
        if speed <= 0:
            raise ValueError("speed mora biti > 0")
        self.speed = speed
        self._wall0 = time.time()
        self._mono0 = time.monotonic()

    def now(self) -> float:
        return self._wall0 + (time.monotonic() - self._mono0) * self.speed

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds / self.speed)


class ManualClock:
    """Sat za testove. Vrijeme se pomice samo rucno, sleep je trenutan."""

    def __init__(self, start: float = 0.0) -> None:
        self._t = start

    def now(self) -> float:
        return self._t

    def advance(self, seconds: float) -> None:
        self._t += seconds

    async def sleep(self, seconds: float) -> None:
        self._t += seconds


def build_clock(simulate: bool, speed: float) -> Clock:
    if simulate and speed != 1.0:
        return ScaledClock(speed)
    return RealClock()
