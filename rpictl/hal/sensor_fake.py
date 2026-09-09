"""Lazni BME680 s termickim modelom prostorije.

Senzor koji vraca konstantnih 22 C ne testira nista. Ovaj ima zatvorenu
petlju: zna radi li ventilator i hladi se dok radi. Tek tako se termostat
stvarno provjerava, a ne samo gleda graf.

Kvarovi se ubrizgavaju preko .fault - to je ono zbog cega simulacija
vrijedi. Da radi kad sve radi znas i bez nje.
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
from dataclasses import dataclass
from typing import Callable

from ..clock import Clock
from ..config import SensorSimConfig
from ..models import Reading, SensorError

log = logging.getLogger(__name__)


@dataclass
class FaultInjection:
    """Prekidaci za kvarove. Mijenjaju se u letu, iz API-ja."""

    freeze: bool = False      # zamrznuto ocitanje -> mora se okinuti watchdog
    error: bool = False       # baca SensorError  -> aplikacija ne smije pasti
    garbage: bool = False     # vraca -40 C       -> mora se odbaciti kao neispravno
    delay_s: float = 0.0      # kasni             -> ne smije blokirati petlju

    def to_dict(self) -> dict:
        return {
            "freeze": self.freeze,
            "error": self.error,
            "garbage": self.garbage,
            "delay_s": self.delay_s,
        }


class FakeTemperatureSensor:
    def __init__(
        self,
        clock: Clock,
        cfg: SensorSimConfig,
        fan_state: Callable[[], bool],
        seed: int | None = 42,
    ) -> None:
        self._clock = clock
        self._cfg = cfg
        self._fan_state = fan_state
        self._rng = random.Random(seed)

        self.fault = FaultInjection()

        self._room_c = cfg.start_c
        self._last_step = clock.now()
        self._frozen: Reading | None = None

    # -- model prostorije ---------------------------------------------------

    def _outdoor_c(self, ts: float) -> float:
        """Dnevna sinusoida: minimum oko 05h, maksimum oko 17h."""
        hour = (ts / 3600.0) % 24.0
        phase = 2.0 * math.pi * (hour - 5.0) / 24.0
        return self._cfg.outdoor_mean_c - self._cfg.outdoor_amp_c * math.cos(phase)

    def _solar_c(self, ts: float) -> float:
        """Sunce grije prostoriju samo danju."""
        hour = (ts / 3600.0) % 24.0
        if 8.0 <= hour <= 18.0:
            return self._cfg.solar_gain_c * math.sin(math.pi * (hour - 8.0) / 10.0)
        return 0.0

    def _step(self, ts: float) -> None:
        minutes = max(0.0, (ts - self._last_step) / 60.0)
        self._last_step = ts
        if minutes == 0.0:
            return

        # Integriramo u koracima od najvise 1 sim-minute da model ostane
        # stabilan i kad je poll_interval velik.
        remaining = minutes
        cursor = ts - minutes * 60.0
        while remaining > 0.0:
            dt = min(1.0, remaining)
            remaining -= dt
            cursor += dt * 60.0
            outdoor = self._outdoor_c(cursor)
            d = self._cfg.k_env * (outdoor - self._room_c) + self._solar_c(cursor)
            if self._fan_state():
                d -= self._cfg.fan_cooling_c
            self._room_c += d * dt

    # -- HAL ----------------------------------------------------------------

    async def read(self) -> Reading:
        if self.fault.delay_s > 0:
            await asyncio.sleep(self.fault.delay_s)

        if self.fault.error:
            raise SensorError("simulirani kvar I2C sabirnice")

        ts = self._clock.now()
        self._step(ts)

        if self.fault.freeze:
            if self._frozen is None:
                self._frozen = Reading(
                    ts=ts, temperature_c=round(self._room_c, 2), humidity_pct=50.0
                )
            # Isti ts kao prvi put -> ocitanje stari, watchdog se mora javiti.
            return self._frozen
        self._frozen = None

        if self.fault.garbage:
            return Reading(ts=ts, temperature_c=-40.0, humidity_pct=0.0)

        temp = self._room_c + self._rng.gauss(0.0, self._cfg.noise_c)
        hum = 55.0 - (temp - 22.0) * 1.5 + self._rng.gauss(0.0, 0.5)
        return Reading(
            ts=ts,
            temperature_c=round(temp, 2),
            humidity_pct=round(max(0.0, min(100.0, hum)), 1),
            pressure_hpa=round(1013.0 + self._rng.gauss(0.0, 0.8), 1),
            gas_ohms=round(50_000 + self._rng.gauss(0.0, 2_000), 0),
        )

    async def close(self) -> None:
        log.debug("lazni senzor zatvoren")

    # -- introspekcija za API -----------------------------------------------

    @property
    def room_c(self) -> float:
        """Prava temperatura modela, bez suma. Za usporedbu s ocitanjem."""
        return self._room_c
