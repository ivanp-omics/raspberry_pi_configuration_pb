"""Pravi relej na GPIO.

Ovdje i samo ovdje zivi prijevod "ventilator neka radi" -> "koji napon na pin".
Kod tvoje sheme ventilator visi na COM-NC, dakle radi kad relej NIJE pobuden,
a modul je vjerojatno active-low. To su dvije neovisne inverzije i lako je
promasiti - zato su obje u konfiguraciji i obje na jednom mjestu.

Napomena o bootu: GPIO17 je pri paljenju Pi-ja ulaz s pull-downom. Ovisno o
modulu relej moze kratko privuci prije nego servis krene. Kod tebe je to
bezopasno (ventilator se ugasi na par sekundi), ali initial_value postavljamo
svjesno, ne slucajno.
"""

from __future__ import annotations

import logging

from ..clock import Clock
from ..config import FanConfig

log = logging.getLogger(__name__)


class GpioRelayFan:
    def __init__(self, clock: Clock, cfg: FanConfig) -> None:
        self._clock = clock
        self._cfg = cfg
        try:
            from gpiozero import OutputDevice  # type: ignore
        except ImportError as exc:  # pragma: no cover - samo na Pi-ju
            raise RuntimeError(
                "nedostaje gpiozero. Na Pi-ju: pip install gpiozero RPi.GPIO"
            ) from exc

        # active_high opisuje modul: kod active-low modula logicka jedinica
        # je nizak napon. gpiozero to preuzima na sebe.
        self._dev = OutputDevice(
            cfg.gpio_pin,
            active_high=cfg.relay_active_high,
            initial_value=self._energised_for(False),
        )
        self._on = False
        self.switch_count = 0
        self.last_change = clock.now()
        log.info(
            "relej na GPIO%d (active_high=%s, ventilator radi kad je pobuden=%s)",
            cfg.gpio_pin,
            cfg.relay_active_high,
            cfg.fan_runs_when_energised,
        )

    def _energised_for(self, fan_on: bool) -> bool:
        """Jedina inverzija u cijelom projektu."""
        return fan_on if self._cfg.fan_runs_when_energised else not fan_on

    @property
    def is_on(self) -> bool:
        return self._on

    @property
    def commanded(self) -> bool:
        return self._on

    async def set(self, on: bool) -> None:
        if on == self._on:
            return
        if self._energised_for(on):
            self._dev.on()
        else:
            self._dev.off()
        self._on = on
        self.switch_count += 1
        self.last_change = self._clock.now()
        log.info("ventilator -> %s", "UKLJUCEN" if on else "iskljucen")

    async def close(self) -> None:
        # Namjerno NE gasimo ventilator na izlazu: otpustanjem releja
        # ventilator se pali, sto je zeljeno stanje kad program ne radi.
        self._dev.close()
