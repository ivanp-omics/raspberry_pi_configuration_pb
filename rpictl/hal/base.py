"""Ugovori koje hardver mora ispuniti.

Protocol umjesto nasljedivanja: lazna i prava implementacija ne dijele
zajednickog pretka, samo isti oblik. Type checker provjerava da se
poklapaju, runtime ne mora znati nista.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from ..models import Host, Reading


@runtime_checkable
class TemperatureSensor(Protocol):
    async def read(self) -> Reading:
        """Jedno ocitanje. Baca SensorError ako ne uspije - nikad ne vraca None."""
        ...

    async def close(self) -> None: ...


@runtime_checkable
class FanControl(Protocol):
    """Namjerno se zove 'fan', a ne 'relay'.

    Servisi razmisljaju o ventilatoru. Cinjenica da se kod tebe ventilator
    vrti kad relej NIJE pobuden zivi iskljucivo u relay_gpio.py. Ako ta
    inverzija procuri u logiku, jednom ces je sigurno zaboraviti.
    """

    @property
    def is_on(self) -> bool: ...

    async def set(self, on: bool) -> None: ...

    async def close(self) -> None: ...


@runtime_checkable
class AudioPlayer(Protocol):
    async def play_file(self, path: Path) -> None: ...

    async def say(self, text: str) -> None: ...

    async def stop(self) -> None: ...

    async def close(self) -> None: ...


@runtime_checkable
class MusicPlayer(Protocol):
    """Pozadinska glazba - odvojen kanal od AudioPlayer najava.

    pause/resume moraju stvarno pustiti/vratiti zvucni uredaj (ne samo
    utisati), inace najava preko AudioPlayer puca s "device busy" na
    hardveru koji ne dijeli izlaz izmedu dva procesa istovremeno.
    """

    @property
    def is_playing(self) -> bool: ...

    @property
    def current_track(self) -> str | None: ...

    @property
    def volume(self) -> int: ...

    async def set_volume(self, level: int) -> None:
        """0-100. Mijenja se uzivo, bez prekida reprodukcije."""
        ...

    async def play(self, track: str | None = None) -> None:
        """track=None pusta cijeli media_dir, promijesan i u petlji."""
        ...

    async def pause(self) -> None: ...

    async def resume(self) -> None: ...

    async def stop(self) -> None: ...

    async def close(self) -> None: ...


@runtime_checkable
class MicRecorder(Protocol):
    """Kratki isjecak s mikrofona - "sto se sad dogada u prostoriji".

    Vraca gotove bajtove audio datoteke, ne tok: trajanje je unaprijed
    odredeno konfiguracijom, pa pozivatelj ne mora upravljati sesijom.
    """

    @property
    def mime(self) -> str:
        """Tip snimke koju ovaj snimac vraca - lazni daje WAV, pravi Opus/Ogg."""
        ...

    async def record(self, seconds: float) -> bytes: ...

    async def close(self) -> None: ...


@runtime_checkable
class NetworkScanner(Protocol):
    async def scan(self) -> list[Host]:
        """Tko je na mrezi sada. Bez pamcenja - povijest vodi inventory servis."""
        ...

    async def close(self) -> None: ...
