"""Prava pozadinska glazba preko mpv-a.

Dugotrajan mpv proces (--idle), upravljan preko JSON-IPC unix socketa umjesto
biblioteke - isti izbor kao u audio_alsa.py (manje ovisnosti, lako se testira
rucno iz shella: `mpv --input-ipc-server=/tmp/x.sock --idle`, pa
`echo '{"command":["loadfile","pjesma.mp3"]}' | socat - /tmp/x.sock`).

Zasto pause() ne postavlja samo pause=yes na mpv-u: jeftini USB zvucni
uredaji i gola ALSA konfiguracija (bez PipeWire-a, kakva je zadana na
Raspberry Pi OS Lite) dopustaju samo jednom procesu odjednom da drzi izlaz.
Da najava (aplay/espeak-ng) ne bi pukla s "device busy" dok mpv drzi uredaj
otvoren u pauzi, pause() umjesto toga zapamti poziciju i stvarno zaustavi
mpv (stop oslobada uredaj); resume() ucita istu datoteku od te pozicije.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from ..config import MusicConfig

log = logging.getLogger(__name__)


def is_stream(track: str) -> bool:
    """Internetski radio ili bilo koji URL koji mpv zna dohvatiti."""
    return track.startswith(("http://", "https://"))


class MpvMusicPlayer:
    def __init__(self, cfg: MusicConfig) -> None:
        self._cfg = cfg
        self._proc: asyncio.subprocess.Process | None = None
        self._track: str | None = None
        self._playing = False
        self._paused_track: str | None = None
        self._paused_pos: float | None = None

    @property
    def is_playing(self) -> bool:
        return self._playing

    @property
    def current_track(self) -> str | None:
        return self._track

    async def _ensure_started(self) -> None:
        if self._proc is not None and self._proc.returncode is None:
            return
        sock = Path(self._cfg.ipc_socket)
        sock.unlink(missing_ok=True)
        cmd = [*self._cfg.player_cmd, f"--input-ipc-server={sock}"]
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
            )
        except FileNotFoundError:
            log.error("nema naredbe %s - instaliraj mpv", cmd[0])
            return
        for _ in range(50):  # do 5 s da mpv otvori IPC socket
            if sock.exists():
                return
            await asyncio.sleep(0.1)
        log.error("mpv nije otvorio IPC socket %s", sock)

    async def _send(self, command: list) -> dict | None:
        sock = Path(self._cfg.ipc_socket)
        if not sock.exists():
            return None
        try:
            reader, writer = await asyncio.open_unix_connection(str(sock))
        except OSError:
            log.exception("ne mogu se spojiti na mpv IPC")
            return None
        try:
            writer.write(json.dumps({"command": command}).encode() + b"\n")
            await writer.drain()
            line = await asyncio.wait_for(reader.readline(), timeout=2.0)
            return json.loads(line) if line else None
        except (asyncio.TimeoutError, OSError, json.JSONDecodeError):
            return None
        finally:
            writer.close()

    async def play(self, track: str | None = None) -> None:
        await self._ensure_started()
        media_dir = Path(self._cfg.media_dir)

        if track and is_stream(track):
            target = track  # mpv sam dohvaca stream, nista ne provjeravamo na disku
        else:
            # Path(track).name rezuje sve sto lici na putanju. Bez toga
            # apsolutna putanja pregazi media_dir (pathlib: "a" / "/etc/x"
            # je "/etc/x") i mpv dobije bilo koju datoteku na uredaju.
            p = media_dir / Path(track).name if track else media_dir
            if not p.exists():
                log.error("nema glazbe: %s", p)
                return
            target = str(p)

        await self._send(["loadfile", target, "replace"])
        if track is None:
            await self._send(["set_property", "shuffle", True])
        await self._send(["set_property", "loop-playlist", "inf"])
        self._track = track
        self._playing = True
        self._paused_track = None
        self._paused_pos = None

    async def pause(self) -> None:
        if not self._playing:
            return
        pos = await self._send(["get_property", "time-pos"])
        path = await self._send(["get_property", "path"])
        self._paused_pos = (pos or {}).get("data")
        self._paused_track = (path or {}).get("data")
        await self._send(["stop"])
        self._playing = False

    async def resume(self) -> None:
        if self._paused_track is None:
            return
        opts = f"start={self._paused_pos}" if self._paused_pos else ""
        cmd = ["loadfile", self._paused_track, "replace"]
        if opts:
            cmd.append(opts)
        await self._send(cmd)
        self._playing = True
        self._paused_track = None
        self._paused_pos = None

    async def stop(self) -> None:
        await self._send(["stop"])
        self._playing = False
        self._track = None
        self._paused_track = None
        self._paused_pos = None

    async def close(self) -> None:
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                self._proc.kill()
        self._proc = None
        self._playing = False
