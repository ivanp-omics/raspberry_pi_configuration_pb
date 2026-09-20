"""Snimanje kratkog isjecka s mikrofona preko ffmpega.

Isti pristup kao kod razglasa (vanjski proces umjesto biblioteke): lako se
provjeri rucno iz shella, i format se mijenja konfiguracijom bez dodiranja
koda. Na uredaju "spremiste" mikrofon je na istoj USB kartici kao i izlaz
(C-Media, card 0) - snimanje i pustanje su odvojeni ALSA smjerovi.

Rucna provjera iste stvari koju radi ovaj modul:
    ffmpeg -nostdin -f alsa -ac 1 -i plughw:0 -t 5 -c:a libopus -f ogg out.ogg
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time

from ..config import ListenConfig
from ..models import MicRecordError

log = logging.getLogger(__name__)


class FfmpegMicRecorder:
    def __init__(self, cfg: ListenConfig) -> None:
        self._cfg = cfg
        self._proc: asyncio.subprocess.Process | None = None
        self._drain: asyncio.Task | None = None
        self._buf = bytearray()
        self._started_at: float | None = None
        self.record_count = 0
        self.last_bytes = 0

    @property
    def mime(self) -> str:
        return self._cfg.mime

    @property
    def recording(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    @property
    def elapsed_s(self) -> float:
        if self._started_at is None:
            return 0.0
        return time.monotonic() - self._started_at

    def _command(self, seconds: float) -> list[str]:
        return [
            *self._cfg.record_cmd,
            "-f", "alsa",
            *self._cfg.input_args,     # prije -i: kako se uredaj OTVARA
            "-i", self._cfg.device,
            "-t", f"{seconds:.2f}",
            *self._cfg.codec_args,     # poslije -i: kako se snimka KODIRA
            "-f", self._cfg.container,
            "pipe:1",
        ]

    async def _pump(self) -> None:
        """Prazni ffmpegov izlaz u memoriju dok traje snimanje.

        Obavezno: cijev prima oko 64 kB, sto je pri 24 kbps nekih 20 sekundi -
        nakon toga bi ffmpeg blokirao na pisanju i snimka bi tiho stala.
        """
        assert self._proc is not None and self._proc.stdout is not None
        while True:
            chunk = await self._proc.stdout.read(8192)
            if not chunk:
                return
            self._buf.extend(chunk)

    async def start(self, max_seconds: float) -> None:
        if self.recording:
            raise MicRecordError("snimanje je vec u tijeku")

        # Granica se predaje ffmpegu (-t), a ne cuva kao Python tajmer: tako se
        # sam zaustavi i uredno zatvori zapis i kad nas nitko ne pita.
        cmd = self._command(max_seconds)
        log.info("slusanje krece: %s", " ".join(cmd))
        self._buf = bytearray()
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            self._proc = None
            raise MicRecordError(
                f"nema naredbe {cmd[0]} - instaliraj ffmpeg (sudo apt install ffmpeg)"
            ) from exc

        self._started_at = time.monotonic()
        self._drain = asyncio.create_task(self._pump())

    async def stop(self) -> bytes:
        proc, drain = self._proc, self._drain
        self._proc = self._drain = None
        self._started_at = None

        if proc is None:
            # Granica je vec istekla i ffmpeg je sam zavrsio - snimka je u
            # meduspremniku i ceka da je netko pokupi.
            if self._buf:
                return self._uzmi_buffer()
            raise MicRecordError("slusanje nije bilo pokrenuto")

        if proc.returncode is None:
            # SIGTERM, ne kill: ffmpeg na njega uredno zatvori Ogg zapis
            # (provjereno na uredaju - ffprobe cita ispravno trajanje).
            proc.terminate()
        if drain is not None:
            try:
                await asyncio.wait_for(drain, timeout=5.0)
            except asyncio.TimeoutError:
                drain.cancel()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()

        if not self._buf:
            err = b""
            if proc.stderr is not None:
                with contextlib.suppress(Exception):
                    err = await proc.stderr.read()
            raise MicRecordError(
                "snimka je prazna - provjeri je li mikrofon prikljucen"
                + (f": {err.decode(errors='replace').strip()[:200]}" if err else "")
            )
        return self._uzmi_buffer()

    def _uzmi_buffer(self) -> bytes:
        data = bytes(self._buf)
        self._buf = bytearray()
        self.record_count += 1
        self.last_bytes = len(data)
        log.info("snimljeno %d B", len(data))
        return data

    async def close(self) -> None:
        if self.recording:
            with contextlib.suppress(MicRecordError):
                await self.stop()
