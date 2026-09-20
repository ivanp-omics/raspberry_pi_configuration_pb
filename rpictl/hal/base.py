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

    @property
    def looping(self) -> bool: ...

    async def start_loop(self, path: Path) -> None:
        """Vrti datoteku u petlji dok je stop_loop() ne prekine (alarm).

        Odvojeno od play_file: ono ceka kraj reprodukcije, a alarm nema kraj.
        Drzi vlastiti proces, pa jednokratna najava i alarm ne dijele isti.
        """
        ...

    async def stop_loop(self) -> None: ...

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

    Sesija u dva koraka (start/stop), a ne jedan blokirajuci poziv: slusanje
    je prekidac, korisnik ga gasi kad zeli. Gornja granica postoji svejedno,
    da mikrofon ne ostane otvoren ako netko zatvori karticu.
    """

    @property
    def mime(self) -> str:
        """Tip snimke koju ovaj snimac vraca - lazni daje WAV, pravi Opus/Ogg."""
        ...

    @property
    def recording(self) -> bool: ...

    @property
    def elapsed_s(self) -> float: ...

    async def start(self, max_seconds: float) -> None: ...

    async def stop(self) -> bytes:
        """Zaustavi i vrati snimljeno. Radi i ako je granica vec istekla -
        snimka se cuva dok je netko ne pokupi."""
        ...

    async def close(self) -> None: ...


@runtime_checkable
class NetworkScanner(Protocol):
    async def scan(self) -> list[Host]:
        """Tko je na mrezi sada. Bez pamcenja - povijest vodi inventory servis."""
        ...

    async def close(self) -> None: ...
