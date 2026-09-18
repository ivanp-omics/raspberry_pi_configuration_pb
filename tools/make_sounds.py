#!/usr/bin/env python3
"""Generira preset zvukove za razglas: media/dingdong.wav i media/alarm.wav.

Zvukovi su sintetizirani, a ne skinuti s interneta, iz dva razloga: nema
pitanja licence/atribucije za javno pustanje u klubu, i parametri (visina,
trajanje, glasnoca) se mijenjaju ovdje pa se skripta samo ponovno pokrene.

Samo standardna biblioteka - nema numpy/scipy ovisnosti.

    python tools/make_sounds.py
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

RATE = 44100
MEDIA = Path(__file__).resolve().parent.parent / "media"


# --------------------------------------------------------------------------
# Zajednicko
# --------------------------------------------------------------------------

def write_wav(path: Path, samples: list[float], peak: float) -> None:
    loudest = max((abs(s) for s in samples), default=0.0) or 1.0
    scale = peak / loudest
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)          # 16-bitni PCM - svira svugdje bez pretvorbe
        fh.setframerate(RATE)
        fh.writeframes(
            b"".join(struct.pack("<h", int(s * scale * 32767)) for s in samples)
        )
    trajanje = len(samples) / RATE
    print(f"{path}  ({path.stat().st_size} B, {trajanje:.1f} s)")


# --------------------------------------------------------------------------
# Zvono: dvotonski "ding dong", opadajuca ovojnica
# --------------------------------------------------------------------------

DING_TONES = (659.25, 523.25)       # E5 -> C5, padajuca velika terca
DING_STARTS = (0.0, 0.42)
DING_DECAY = 0.38
DING_TOTAL = 1.9
# Blago rastegnuti visi parcijali (2.01, 3.02) umjesto tocnih visekratnika su
# ono sto metalnim udaraljkama daje karakter - cisti sinus zvuci kao test ton.
DING_PARTIALS = ((1.00, 1.00), (2.01, 0.42), (3.02, 0.16))
ATTACK_S = 0.004                    # kratki napad da nema "klika" na pocetku


def dingdong() -> list[float]:
    samples = [0.0] * int(DING_TOTAL * RATE)
    for freq, start in zip(DING_TONES, DING_STARTS):
        offset = int(start * RATE)
        for i in range(offset, len(samples)):
            t = (i - offset) / RATE
            # Prekid se mjeri po krivulji gasenja, PRIJE mnozenja s napadom -
            # inace je na t=0 napad tocno 0 i petlja stane odmah.
            decay = math.exp(-t / DING_DECAY)
            if decay < 1e-4:
                break
            env = decay
            if t < ATTACK_S:
                env *= t / ATTACK_S
            samples[i] += env * sum(
                amp * math.sin(2.0 * math.pi * freq * mult * t)
                for mult, amp in DING_PARTIALS
            )
    return samples


# --------------------------------------------------------------------------
# Alarm: klasicna dvotonska sirena
# --------------------------------------------------------------------------

ALARM_TONES = (440.0, 660.0)        # kvinta - klasican "hitna sluzba" par
ALARM_NOTE_S = 0.5
ALARM_CYCLES = 4                    # 4 x (dva tona) = 4 s
ALARM_EDGE_S = 0.008                # napad/otpustanje po tonu, protiv klikova
# Vise harmonika nego kod zvona i RAVNA ovojnica: to je ono sto sirenu cini
# probojnom kroz zvukove dvorane, vise nego sama amplituda.
ALARM_PARTIALS = ((1.00, 1.00), (2.00, 0.55), (3.00, 0.30), (4.00, 0.14))


def alarm() -> list[float]:
    samples: list[float] = []
    for _ in range(ALARM_CYCLES):
        for freq in ALARM_TONES:
            n = int(ALARM_NOTE_S * RATE)
            edge = max(1, int(ALARM_EDGE_S * RATE))
            for i in range(n):
                t = i / RATE
                if i < edge:                      # napad
                    env = i / edge
                elif i > n - edge:                # otpustanje
                    env = (n - i) / edge
                else:                             # ravan, sustained dio
                    env = 1.0
                samples.append(env * sum(
                    amp * math.sin(2.0 * math.pi * freq * mult * t)
                    for mult, amp in ALARM_PARTIALS
                ))
    return samples


def main() -> None:
    # Alarm je glasniji od zvona (0.95 vs 0.82) - namjerno, to mu je posao.
    write_wav(MEDIA / "dingdong.wav", dingdong(), peak=0.82)
    write_wav(MEDIA / "alarm.wav", alarm(), peak=0.95)


if __name__ == "__main__":
    main()
