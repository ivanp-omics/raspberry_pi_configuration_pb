"""Datoteke za razglas i glazbu: popis, spremanje, brisanje.

Nema hardvera ni asyncio petlje - obicna posluga oko dvije mape, pa stoji uz
bus.py i clock.py, a ne medu servisima.

Sve provjere imena su ovdje jer je ovo jedino mjesto u projektu gdje ime
datoteke stize izvana. Path(name).name rezuje sve sto lici na putanju: bez
toga apsolutna putanja u pathlibu pregazi cijelu bazu ("media" / "/etc/shadow"
je "/etc/shadow"), pa bi player dobio bilo koju datoteku na uredaju.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

# Razglas svira preko mpv-a (vidi AudioConfig.player_cmd), koji cita sve ovo.
# webm/ogg/m4a su tu jer MediaRecorder u browseru ne zna snimati u WAV - svaki
# browser daje svoj kontejner (Chrome webm, Firefox ogg, Safari m4a).
ANNOUNCE_EXT = frozenset({".wav", ".webm", ".ogg", ".m4a", ".opus", ".mp3"})
MUSIC_EXT = frozenset({".mp3", ".wav", ".flac", ".ogg", ".m4a", ".opus"})
MAX_BYTES = 25 * 1024 * 1024

_SAFE_NAME = re.compile(r"^[A-Za-z0-9 ._-]{1,100}$")


class MediaError(ValueError):
    """Ime, vrsta ili velicina datoteke nisu prihvatljivi."""


class MediaLibrary:
    def __init__(self, announce_dir: str, music_dir: str) -> None:
        self._dirs = {"announce": Path(announce_dir), "music": Path(music_dir)}
        for d in self._dirs.values():
            d.mkdir(parents=True, exist_ok=True)

    def _dir(self, kind: str) -> Path:
        try:
            return self._dirs[kind]
        except KeyError:
            raise MediaError("vrsta mora biti 'announce' ili 'music'") from None

    def _safe_name(self, kind: str, filename: str) -> str:
        name = Path(filename).name
        if not _SAFE_NAME.match(name):
            raise MediaError(
                "ime smije sadrzavati samo slova, brojke, razmak, tocku, _ i -"
            )
        allowed = ANNOUNCE_EXT if kind == "announce" else MUSIC_EXT
        if Path(name).suffix.lower() not in allowed:
            raise MediaError(f"dopusteni nastavci: {', '.join(sorted(allowed))}")
        return name

    def list(self, kind: str) -> list[dict]:
        return [
            {"name": p.name, "bytes": p.stat().st_size}
            for p in sorted(self._dir(kind).iterdir())
            if p.is_file()
        ]

    def save(self, kind: str, filename: str, data: bytes) -> str:
        name = self._safe_name(kind, filename)
        if not data:
            raise MediaError("datoteka je prazna")
        if len(data) > MAX_BYTES:
            raise MediaError(f"datoteka prelazi {MAX_BYTES // 1024 // 1024} MB")
        path = self._dir(kind) / name
        path.write_bytes(data)
        log.info("spremljeno %s (%d B)", path, len(data))
        return name

    def delete(self, kind: str, filename: str) -> None:
        path = self._dir(kind) / Path(filename).name
        if not path.is_file():
            raise MediaError(f"nema datoteke '{Path(filename).name}'")
        path.unlink()
        log.info("obrisano %s", path)
