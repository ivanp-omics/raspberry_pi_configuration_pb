"""Lazni ventilator. Pamti stanje, broji paljenja, zna se zaglaviti."""

from __future__ import annotations

import logging

from ..clock import Clock

log = logging.getLogger(__name__)


class FakeFan:
    # Default je "radi", isto kao pravi relej (vidi relay_gpio.py): i hardver
    # i ThermostatPolicy krecu odatle, pa simulacija modelira isti start.
    def __init__(self, clock: Clock, initial: bool = True) -> None:
        self._clock = clock
        self._on = initial
        self.switch_count = 0
        self.stuck_on = False   # simulira zalijepljen relej
        self.last_change = clock.now()

    @property
    def is_on(self) -> bool:
        return True if self.stuck_on else self._on

    @property
    def commanded(self) -> bool:
        """Sto smo naredili - moze se razlikovati od is_on ako je zaglavljen."""
        return self._on

    async def set(self, on: bool) -> None:
        if on == self._on:
            return
        self._on = on
        self.switch_count += 1
        self.last_change = self._clock.now()
        log.info("ventilator -> %s", "UKLJUCEN" if on else "iskljucen")

    async def close(self) -> None:
        await self.set(False)
