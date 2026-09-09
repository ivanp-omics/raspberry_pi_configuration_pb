"""Podatkovni tipovi koji putuju kroz sustav.

Namjerno su glupi: bez logike, bez I/O. Dijele ih HAL, servisi i API.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any


class SensorError(RuntimeError):
    """Senzor nije uspio dati ocitanje. Servisi ovo hvataju i ne padaju."""


@dataclass(frozen=True, slots=True)
class Reading:
    """Jedno ocitanje senzora. ts je vrijeme po Clock-u, ne po time.time()."""

    ts: float
    temperature_c: float
    humidity_pct: float | None = None
    pressure_hpa: float | None = None
    gas_ohms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Host:
    """Uredaj vidljiv na mrezi u ovom trenutku."""

    mac: str
    ip: str
    hostname: str | None = None


@dataclass(slots=True)
class HostRecord:
    """Uredaj s povijescu - ovo je ono sto inventory servis pamti."""

    mac: str
    ip: str
    hostname: str | None
    first_seen: float
    last_seen: float
    online: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FanMode(str, Enum):
    AUTO = "auto"
    ON = "on"
    OFF = "off"


class Priority(int, Enum):
    """Manji broj = ide prije."""

    ALARM = 0
    NORMAL = 5
    LOW = 9


@dataclass(frozen=True, slots=True)
class Announcement:
    id: str
    priority: Priority
    text: str | None = None
    path: str | None = None


# Tipovi dogadaja na busu. Stringovi, jer idu ravno u JSON prema browseru.
EV_READING = "reading"
EV_FAN = "fan"
EV_ANNOUNCE = "announce"
EV_NETWORK = "network"
EV_FAULT = "fault"
EV_MUSIC = "music"
