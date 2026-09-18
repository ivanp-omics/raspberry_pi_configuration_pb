"""Snimanje kratkog isjecka s mikrofona preko ffmpega.

Isti pristup kao kod razglasa (vanjski proces umjesto biblioteke): lako se
provjeri rucno iz shella, i format se mijenja konfiguracijom bez dodiranja
koda. Na uredaju "spremiste" mikrofon je na istoj USB kartici kao i izlaz
(C-Media, card 0) - snimanje i pustanje su odvojeni ALSA smjerovi.

Rucna provjera iste stvari koju radi ovaj modul:
    ffmpeg -nostdin -f alsa -i hw:0 -t 10 -ac 1 -c:a libopus -f ogg out.ogg
"""

from __future__ import annotations

import asyncio
import logging

from ..config import ListenConfig
from ..models import MicRecordError

log = logging.getLogger(__name__)


class FfmpegMicRecorder:
    def __init__(self, cfg: ListenConfig) -> None:
        self._cfg = cfg
        self.record_count = 0
        self.last_bytes = 0

    @property
    def mime(self) -> str:
        return self._cfg.mime

    def _command(self, seconds: float) -> list[str]:
        return [
            *self._cfg.record_cmd,
            "-f", "alsa",
            "-i", self._cfg.device,
            "-t", f"{seconds:.2f}",
            *self._cfg.codec_args,
            "-f", self._cfg.container,
            "pipe:1",
        ]

    async def record(self, seconds: float) -> bytes:
        cmd = self._command(seconds)
        log.info("snimanje isjecka: %s", " ".join(cmd))
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise MicRecordError(
                f"nema naredbe {cmd[0]} - instaliraj ffmpeg (sudo apt install ffmpeg)"
            ) from exc

        # Timeout je duzi od trajanja snimke: ffmpeg treba i vrijeme da otvori
        # uredaj i zatvori kontejner. Bez njega zauzet mikrofon zaglavi zahtjev.
        try:
            data, err = await asyncio.wait_for(
                proc.communicate(), timeout=seconds + 10.0
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise MicRecordError("snimanje nije zavrsilo na vrijeme") from None

        if proc.returncode != 0:
            raise MicRecordError(
                f"ffmpeg je vratio {proc.returncode}: "
                f"{err.decode(errors='replace').strip()[:300]}"
            )
        if not data:
            raise MicRecordError("snimka je prazna - provjeri je li mikrofon prikljucen")

        self.record_count += 1
        self.last_bytes = len(data)
        log.info("snimljeno %d B", len(data))
        return data

    async def close(self) -> None:
        return None
