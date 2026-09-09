"""Termostat.

Podijeljen na dva dijela, i to je najvaznija odluka u ovoj datoteci:

  ThermostatPolicy  - cista sinkrona odluka. Bez I/O, bez asyncio, bez sata.
                      Vrijeme joj se predaje kao broj. Zato se osam sati rada
                      testira u milisekundama.
  ClimateService    - asyncio petlja koja cita senzor, zove politiku i pomice
                      ventilator. Nema pravila u sebi.

Bugovi u ovakvom sustavu gotovo uvijek su u pravilima, a ne u petlji.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..bus import Bus
from ..clock import Clock
from ..config import ClimateConfig
from ..hal.base import FanControl, TemperatureSensor
from ..models import EV_FAN, EV_FAULT, EV_READING, FanMode, Reading, SensorError

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Decision:
    fan_on: bool
    reason: str
    healthy: bool          # False = radimo na fail-safeu, senzoru se ne vjeruje


class ThermostatPolicy:
    """Histereza + minimalna vremena + fail-safe. Nista vise."""

    def __init__(self, cfg: ClimateConfig) -> None:
        self.cfg = cfg
        # Pocinjemo s ukljucenim ventilatorom: dok ne znamo temperaturu,
        # sigurnije je hladiti nego ne hladiti. Isto stanje u koje sklop
        # pada kad Pi crkne, pa je ponasanje dosljedno.
        self._fan_on = True
        self._changed_at = float("-inf")
        self.cycles = 0

    @property
    def fan_on(self) -> bool:
        return self._fan_on

    def _commit(self, now: float, want: bool, reason: str, healthy: bool) -> Decision:
        if want != self._fan_on:
            self._fan_on = want
            self._changed_at = now
            self.cycles += 1
        return Decision(fan_on=self._fan_on, reason=reason, healthy=healthy)

    def decide(self, now: float, reading: Reading | None, mode: FanMode) -> Decision:
        if mode is FanMode.ON:
            return self._commit(now, True, "rucno ukljuceno", True)
        if mode is FanMode.OFF:
            return self._commit(now, False, "rucno iskljuceno", True)

        # --- provjere ispravnosti ocitanja; svaka pada na sigurnu stranu ---
        if reading is None:
            return self._commit(now, True, "nema ocitanja", False)

        age = now - reading.ts
        if age > self.cfg.stale_after_s:
            return self._commit(
                now, True, f"ocitanje staro {age:.0f} s", False
            )

        t = reading.temperature_c
        if not (self.cfg.valid_min_c <= t <= self.cfg.valid_max_c):
            return self._commit(
                now, True, f"ocitanje izvan raspona ({t:.1f} C)", False
            )

        # --- histereza ---
        want = self._fan_on
        if t >= self.cfg.temp_on_c:
            want = True
        elif t <= self.cfg.temp_off_c:
            want = False

        if want == self._fan_on:
            return Decision(self._fan_on, f"{t:.1f} C, bez promjene", True)

        # --- minimalna vremena: sprjecavaju trzanje oko praga ---
        elapsed = now - self._changed_at
        if self._fan_on and elapsed < self.cfg.min_on_s:
            return Decision(
                True, f"{t:.1f} C, ali minimalno vrijeme rada jos traje", True
            )
        if not self._fan_on and elapsed < self.cfg.min_off_s:
            return Decision(
                False, f"{t:.1f} C, ali minimalno vrijeme mirovanja jos traje", True
            )

        return self._commit(
            now, want, f"{t:.1f} C -> {'paljenje' if want else 'gasenje'}", True
        )


class ClimateService:
    """Jedini vlasnik ventilatora. Nitko drugi ne smije zvati fan.set()."""

    name = "climate"

    def __init__(
        self,
        cfg: ClimateConfig,
        clock: Clock,
        bus: Bus,
        sensor: TemperatureSensor,
        fan: FanControl,
    ) -> None:
        self.cfg = cfg
        self.policy = ThermostatPolicy(cfg)
        self._clock = clock
        self._bus = bus
        self._sensor = sensor
        self._fan = fan

        self.mode = FanMode.AUTO
        self.last_reading: Reading | None = None
        self.last_decision: Decision | None = None
        self.error_count = 0
        self.read_count = 0

    async def set_mode(self, mode: FanMode) -> None:
        """Mijenja nacin rada i odmah ga primjenjuje.

        Bez trenutne primjene korisnik pritisne gumb i do sljedeceg ciklusa
        vidi staro stanje - izgleda kao da sucelje ne radi.
        """
        log.info("nacin rada -> %s", mode.value)
        self.mode = mode
        await self._apply()

    async def _apply(self) -> None:
        """Odluci i pomakni ventilator. Ne cita senzor."""
        now = self._clock.now()
        before = self._fan.is_on
        decision = self.policy.decide(now, self.last_reading, self.mode)
        self.last_decision = decision

        if decision.fan_on != before:
            await self._fan.set(decision.fan_on)
            self._bus.publish(
                EV_FAN,
                {
                    "on": decision.fan_on,
                    "reason": decision.reason,
                    "healthy": decision.healthy,
                    "ts": now,
                },
            )

    async def _tick(self) -> None:
        try:
            reading = await self._sensor.read()
            self.last_reading = reading
            self.read_count += 1
            self._bus.publish(EV_READING, reading.to_dict())
        except SensorError as exc:
            # Kvar senzora ne smije srusiti aplikaciju. Zadrzavamo zadnje
            # ocitanje - politika ce ga sama proglasiti zastarjelim.
            self.error_count += 1
            log.warning("senzor: %s", exc)
            self._bus.publish(EV_FAULT, {"source": "sensor", "message": str(exc)})

        await self._apply()

    async def run(self) -> None:
        log.info(
            "termostat: pali na %.1f C, gasi na %.1f C, min %ds/%ds",
            self.cfg.temp_on_c, self.cfg.temp_off_c,
            int(self.cfg.min_on_s), int(self.cfg.min_off_s),
        )
        while True:
            try:
                await self._tick()
            except Exception:  # noqa: BLE001 - petlja se ne smije prekinuti
                log.exception("neocekivana greska u klima petlji")
            await self._clock.sleep(self.cfg.poll_interval_s)

    def snapshot(self) -> dict:
        d = self.last_decision
        return {
            "mode": self.mode.value,
            "fan_on": self._fan.is_on,
            "reason": d.reason if d else "jos nema odluke",
            "healthy": d.healthy if d else False,
            "reading": self.last_reading.to_dict() if self.last_reading else None,
            "reading_age_s": (
                self._clock.now() - self.last_reading.ts if self.last_reading else None
            ),
            "cycles": self.policy.cycles,
            "reads": self.read_count,
            "errors": self.error_count,
            "thresholds": {
                "on_c": self.cfg.temp_on_c,
                "off_c": self.cfg.temp_off_c,
            },
        }
