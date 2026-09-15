"""Pravi relej na GPIO.

Ovdje i samo ovdje zivi prijevod "ventilator neka radi" -> "koji napon na pin".
Dvije neovisne inverzije, obje iz konfiguracije: kakav je modul
(`relay_active_high`) i kako je ventilator ozicen (`fan_runs_when_energised`).
Obje se lako promase, pa se mjere multimetrom, ne pretpostavljaju.

Na uredaju "spremiste" (izmjereno 12.9.2026): Joy-it modul je active-HIGH,
ventilator na NC kontaktu -> pin LOW = relej otpusten = ventilator radi.

Napomena o bootu: `config.txt` ima `gpio=17=op,dl`, pa firmware drzi pin LOW
i ventilator radi kroz cijeli boot. Zato initial_value krece od "ventilator
radi" - inace bi ga pokretanje servisa nakratko ugasilo, sto je nepotreban
ciklus releja pri svakom restartu (a servis ima Restart=always).
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
                "nedostaje gpiozero. Na Pi-ju (Trixie): "
                "sudo apt install python3-gpiozero python3-lgpio"
            ) from exc

        # active_high opisuje modul: kod active-low modula logicka jedinica
        # je nizak napon. gpiozero to preuzima na sebe.
        #
        # Krecemo od "ventilator radi": to je stanje u kojem firmware ostavi
        # pin (gpio=17=op,dl) i stanje s kojim ThermostatPolicy krece, pa se
        # pri pokretanju servisa relej uopce ne pomakne. Prvi tick odmah
        # nakon toga donese pravu odluku na temelju ocitanja.
        self._dev = OutputDevice(
            cfg.gpio_pin,
            active_high=cfg.relay_active_high,
            initial_value=self._energised_for(True),
        )
        self._on = True
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
