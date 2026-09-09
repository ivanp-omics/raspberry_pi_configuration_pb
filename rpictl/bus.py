"""Minimalni pub/sub izmedu servisa.

Pravilo arhitekture: servisi se ne pozivaju medusobno. Klima objavi da je
izmjerila 25.3 C, a tko god to treba - telemetrija, WebSocket, najave -
sam se pretplati. Tako dodavanje novog potrosaca ne dira postojeci kod.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

log = logging.getLogger(__name__)


class Bus:
    def __init__(self, queue_size: int = 200) -> None:
        self._queue_size = queue_size
        self._subs: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._queue_size)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def publish(self, event_type: str, data: dict[str, Any]) -> None:
        """Nikad ne blokira. Spori pretplatnik gubi poruke, ne kroci sustav."""
        msg = {"type": event_type, "data": data}
        for q in list(self._subs):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                log.warning("pretplatnik ne stize citati, bacam dogadaj %s", event_type)

    @property
    def subscriber_count(self) -> int:
        return len(self._subs)
