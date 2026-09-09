"""Tko je na mrezi.

Skener vraca samo trenutno stanje. Ovaj servis dodaje pamcenje: kad je tko
prvi put vidjen, kad zadnji, i javlja kad se nesto promijeni.
"""

from __future__ import annotations

import logging

from ..bus import Bus
from ..clock import Clock
from ..config import NetworkConfig
from ..hal.base import NetworkScanner
from ..models import EV_NETWORK, HostRecord

log = logging.getLogger(__name__)


class InventoryService:
    name = "inventory"

    def __init__(
        self, cfg: NetworkConfig, clock: Clock, bus: Bus, scanner: NetworkScanner
    ) -> None:
        self.cfg = cfg
        self._clock = clock
        self._bus = bus
        self._scanner = scanner
        self.hosts: dict[str, HostRecord] = {}
        self.last_scan: float | None = None
        self.scan_count = 0

    async def _tick(self) -> None:
        found = await self._scanner.scan()
        now = self._clock.now()
        self.last_scan = now
        self.scan_count += 1

        seen = set()
        appeared: list[str] = []
        for h in found:
            seen.add(h.mac)
            rec = self.hosts.get(h.mac)
            if rec is None:
                self.hosts[h.mac] = HostRecord(
                    mac=h.mac, ip=h.ip, hostname=h.hostname,
                    first_seen=now, last_seen=now, online=True,
                )
                appeared.append(h.mac)
                log.info("novi uredaj: %s (%s)", h.hostname or h.mac, h.ip)
            else:
                rec.ip = h.ip
                rec.hostname = h.hostname or rec.hostname
                rec.last_seen = now
                if not rec.online:
                    rec.online = True
                    appeared.append(h.mac)

        disappeared = [m for m, r in self.hosts.items() if r.online and m not in seen]
        for mac in disappeared:
            self.hosts[mac].online = False
            log.info("nestao uredaj: %s", self.hosts[mac].hostname or mac)

        if appeared or disappeared:
            self._bus.publish(EV_NETWORK, {
                "appeared": appeared, "disappeared": disappeared,
                "online": sum(1 for r in self.hosts.values() if r.online),
            })

    async def run(self) -> None:
        while True:
            try:
                await self._tick()
            except Exception:  # noqa: BLE001
                log.exception("greska u skeniranju mreze")
            await self._clock.sleep(self.cfg.scan_interval_s)

    def snapshot(self) -> dict:
        return {
            "last_scan": self.last_scan,
            "scans": self.scan_count,
            "online": sum(1 for r in self.hosts.values() if r.online),
            "known": len(self.hosts),
            "hosts": [r.to_dict() for r in sorted(
                self.hosts.values(), key=lambda r: (not r.online, r.ip)
            )],
        }
