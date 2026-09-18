"""Zdravlje samog uredaja, ne prostorije.

Temperatura SoC-a se cita iz sysfsa, a ne preko `vcgencmd`: sysfs ne trazi
nikakva prava ni clanstvo u grupi `video`, i radi jednako na svakom Linuxu.
Izvan Pi-ja datoteka ne postoji, pa funkcija vrati None i sucelje taj redak
jednostavno ne prikaze - nema potrebe za HAL protokolom i laznom izvedbom
zbog jednog broja.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

# Vrijednost je u tisucinkama stupnja: 48312 znaci 48.3 C.
THERMAL_FILE = Path("/sys/class/thermal/thermal_zone0/temp")

# Raspberry Pi pocinje usporavati oko 80 C; 70 je razumna granica za upozorenje.
WARN_C = 70.0
THROTTLE_C = 80.0


def cpu_temperature_c() -> float | None:
    try:
        raw = THERMAL_FILE.read_text(encoding="ascii").strip()
    except OSError:
        return None
    try:
        return round(int(raw) / 1000.0, 1)
    except ValueError:
        log.warning("neocekivan sadrzaj %s: %r", THERMAL_FILE, raw[:40])
        return None
