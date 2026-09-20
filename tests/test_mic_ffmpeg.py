"""Testovi pravog (ffmpeg) snimaca - bez ffmpega.

Lazni snimac ne izvrsava ovaj kod, pa je ostao nepokriven sve dok na uredaju
nije pao s 500. Ovdje se cilja bas ta mjesta: praznjenje izlaznog toka i
sastavljanje naredbe.
"""

from __future__ import annotations

import asyncio

import pytest

from rpictl.config import ListenConfig
from rpictl.hal.mic_ffmpeg import FfmpegMicRecorder


class _LazniTok:
    """Glumi asyncio.StreamReader: vraca zadane komade pa EOF."""

    def __init__(self, komadi: list[bytes]) -> None:
        self._komadi = list(komadi)

    async def read(self, _n: int) -> bytes:
        await asyncio.sleep(0)
        return self._komadi.pop(0) if self._komadi else b""


async def test_pump_ne_ovisi_o_self_proc():
    """Regresija: stop() ocisti self._proc prije cekanja na ovaj zadatak.

    Dok je _pump citao self._proc u svakoj iteraciji, sljedeci prolaz je pao
    na None.stdout i cijeli zahtjev je zavrsio kao 500.
    """
    rec = FfmpegMicRecorder(ListenConfig())
    tok = _LazniTok([b"aa", b"bb", b"cc"])
    zadatak = asyncio.create_task(rec._pump(tok))

    await asyncio.sleep(0)
    rec._proc = None          # ovo je rusilo snimanje

    await asyncio.wait_for(zadatak, timeout=1.0)
    assert bytes(rec._buf) == b"aabbcc"


async def test_pump_staje_na_eof():
    rec = FfmpegMicRecorder(ListenConfig())
    await asyncio.wait_for(rec._pump(_LazniTok([b"x"])), timeout=1.0)
    assert bytes(rec._buf) == b"x"


def test_naredba_ima_mono_prije_ulaza():
    """-ac 1 mora ici PRIJE -i (otvaranje uredaja), a plughw rjesava mono/stereo."""
    cmd = FfmpegMicRecorder(ListenConfig())._command(30.0)
    assert cmd[cmd.index("-i") - 2 : cmd.index("-i")] == ["-ac", "1"]
    assert cmd[cmd.index("-i") + 1].startswith("plughw"), "hw: odbija mono mikrofon"
    assert "-t" in cmd and cmd[cmd.index("-t") + 1] == "30.00"
    assert cmd[-1] == "pipe:1"


@pytest.mark.parametrize("stanje", ["prazan", "nakon_stopa"])
async def test_stop_bez_pokrenutog_snimanja(stanje):
    rec = FfmpegMicRecorder(ListenConfig())
    if stanje == "nakon_stopa":
        rec._buf = bytearray()
    from rpictl.models import MicRecordError

    with pytest.raises(MicRecordError):
        await rec.stop()


async def test_stop_vraca_zapamcenu_snimku_nakon_isteka_granice():
    """Kad ffmpeg sam zavrsi (granica), snimka ceka u meduspremniku."""
    rec = FfmpegMicRecorder(ListenConfig())
    rec._buf = bytearray(b"snimljeno")
    assert await rec.stop() == b"snimljeno"
    assert rec.last_bytes == 9
