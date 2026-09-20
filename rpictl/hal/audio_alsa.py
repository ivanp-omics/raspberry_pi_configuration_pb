"""Pravi razglas preko 3.5 mm izlaza.

Vanjski procesi (aplay, espeak-ng) umjesto biblioteke: manje ovisnosti,
lakse zamijeniti, i lako se testira rucno iz shella.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from ..config import AudioConfig

log = logging.getLogger(__name__)


class AlsaAudioPlayer:
    def __init__(self, cfg: AudioConfig) -> None:
        self._cfg = cfg
        self._proc: asyncio.subprocess.Process | None = None
        # Alarm ima vlastiti proces: play_file ceka kraj reprodukcije, a alarm
        # nema kraj dok ga netko ne ugasi.
        self._loop_proc: asyncio.subprocess.Process | None = None
        self.now_playing: str | None = None
        self.play_count = 0

    @property
    def looping(self) -> bool:
        return self._loop_proc is not None and self._loop_proc.returncode is None

    async def start_loop(self, path: Path) -> None:
        await self.stop_loop()
        full = Path(self._cfg.media_dir) / Path(path).name
        if not full.exists():
            log.error("nema zvucne datoteke za petlju: %s", full)
            return
        cmd = [*self._cfg.player_cmd, *self._cfg.loop_args, str(full)]
        log.info("petlja: %s", " ".join(cmd))
        try:
            self._loop_proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except FileNotFoundError:
            log.error("nema naredbe %s - instaliraj mpv", cmd[0])
            self._loop_proc = None

    async def stop_loop(self) -> None:
        proc = self._loop_proc
        self._loop_proc = None
        if proc is None or proc.returncode is not None:
            return
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            proc.kill()

    async def _run(self, cmd: list[str], label: str) -> None:
        await self.stop()
        self.now_playing = label
        self.play_count += 1
        log.info("razglas: %s", " ".join(cmd))
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, err = await self._proc.communicate()
            if self._proc.returncode not in (0, -15):
                log.error("razglas nije uspio: %s", err.decode(errors="replace").strip())
        except FileNotFoundError:
            log.error("nema naredbe %s - instaliraj alsa-utils / espeak-ng", cmd[0])
        finally:
            self._proc = None
            self.now_playing = None

    async def play_file(self, path: Path) -> None:
        full = Path(self._cfg.media_dir) / Path(path).name
        if not full.exists():
            log.error("nema zvucne datoteke: %s", full)
            return
        await self._run([*self._cfg.player_cmd, str(full)], f"datoteka {full.name}")

    async def say(self, text: str) -> None:
        await self._run([*self._cfg.tts_cmd, text], f'govor "{text[:40]}"')

    async def stop(self) -> None:
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                self._proc.kill()
        self.now_playing = None

    async def close(self) -> None:
        await self.stop_loop()
        await self.stop()
