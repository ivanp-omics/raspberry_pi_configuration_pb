"""Lazni skener mreze.

Fiksna lista, ali s namjernim mrdanjem: jedan uredaj povremeno nestane,
jedan novi se pojavi. Bez toga inventory servis nikad ne pokaze da zna
detektirati promjenu.
"""

from __future__ import annotations

import random

from ..models import Host

_BASE = [
    Host("b8:27:eb:11:22:33", "192.168.1.10", "rpictl"),
    Host("d8:3a:dd:44:55:66", "192.168.1.1", "router"),
    Host("a4:cf:12:77:88:99", "192.168.1.20", "shelly-vrata"),
    Host("e8:db:84:aa:bb:cc", "192.168.1.21", "shelly-rasvjeta"),
    Host("3c:22:fb:dd:ee:ff", "192.168.1.55", "laptop-ivan"),
]

_INTRUDER = Host("00:1a:2b:33:44:55", "192.168.1.99", None)


class FakeNetworkScanner:
    def __init__(self, seed: int | None = 7) -> None:
        self._rng = random.Random(seed)
        self.scan_count = 0

    async def scan(self) -> list[Host]:
        self.scan_count += 1
        hosts = list(_BASE)
        # laptop se spaja i odspaja
        if self._rng.random() < 0.35:
            hosts.remove(_BASE[4])
        # povremeno nepoznat uredaj
        if self._rng.random() < 0.20:
            hosts.append(_INTRUDER)
        return hosts

    async def close(self) -> None:
        return None
