#!/usr/bin/env python3
"""Generira media/dingdong.wav - dvotonski zvon za preset gumb na razglasu.

Zvuk je sintetiziran, a ne skinut s interneta, iz dva razloga: nema pitanja
licence/atribucije za javno puštanje u klubu, i parametri (visina tona,
trajanje, glasnoca) se mijenjaju ovdje pa se skripta samo ponovno pokrene.

Samo standardna biblioteka - nema numpy/scipy ovisnosti.

    python tools/make_dingdong.py
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

RATE = 44100
OUT = Path(__file__).resolve().parent.parent / "media" / "dingdong.wav"

# Klasican zvon vrata: padajuca velika terca. E5 -> C5.
TONE_HZ = (659.25, 523.25)
TONE_START_S = (0.0, 0.42)      # kad koji ton krece
DECAY_S = 0.38                  # konstanta eksponencijalnog gasenja
ATTACK_S = 0.004                # kratki napad da nema "klika" na pocetku
TOTAL_S = 1.9
PEAK = 0.82                     # ostavlja malo zracnog prostora do clippinga

# Parcijali daju "zvonasti" karakter - cisti sinus zvuci kao test ton, ne zvono.
# Blago rastegnuti visi parcijali (2.01, 3.02) umjesto tocnih visekratnika su
# ono sto metalnim udaraljkama daje karakter.
PARTIALS = ((1.00, 1.00), (2.01, 0.42), (3.02, 0.16))


def render() -> list[float]:
    samples = [0.0] * int(TOTAL_S * RATE)
    for freq, start in zip(TONE_HZ, TONE_START_S):
        offset = int(start * RATE)
        for i in range(offset, len(samples)):
            t = (i - offset) / RATE
            # Prekid se mjeri po samoj krivulji gasenja, PRIJE mnozenja s
            # napadom - inace je na t=0 napad tocno 0 i petlja stane odmah.
            decay = math.exp(-t / DECAY_S)
            if decay < 1e-4:
                break
            env = decay
            if t < ATTACK_S:
                env *= t / ATTACK_S
            value = sum(
                amp * math.sin(2.0 * math.pi * freq * mult * t)
                for mult, amp in PARTIALS
            )
            samples[i] += value * env
    return samples


def normalise(samples: list[float]) -> list[float]:
    loudest = max(abs(s) for s in samples) or 1.0
    scale = PEAK / loudest
    return [s * scale for s in samples]


def main() -> None:
    samples = normalise(render())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)          # 16-bitni PCM - aplay ovo cita bez ikakve pretvorbe
        fh.setframerate(RATE)
        fh.writeframes(b"".join(struct.pack("<h", int(s * 32767)) for s in samples))
    print(f"{OUT}  ({OUT.stat().st_size} B, {TOTAL_S} s, {RATE} Hz mono)")


if __name__ == "__main__":
    main()
