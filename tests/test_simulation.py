"""Testovi lazne opreme i servisa nad njom.

Poanta simulacije nije "radi kad sve radi" - to znas i bez nje - nego sto
se dogodi kad pukne.
"""

from __future__ import annotations

import asyncio

import pytest

from rpictl.bus import Bus
from rpictl.clock import ManualClock
from rpictl.config import ClimateConfig, SensorSimConfig
from rpictl.hal.music_fake import FakeMusicPlayer
from rpictl.hal.relay_fake import FakeFan
from rpictl.hal.sensor_fake import FakeTemperatureSensor
from rpictl.models import EV_READING, FanMode, SensorError
from rpictl.services.announcer import AnnouncerService
from rpictl.services.climate import ClimateService
from rpictl.services.music import MusicService

pytestmark = pytest.mark.asyncio


def build(**climate_kw):
    clock = ManualClock(start=12 * 3600.0)   # podne
    fan = FakeFan(clock)
    sensor = FakeTemperatureSensor(
        clock, SensorSimConfig(start_c=23.0), fan_state=lambda: fan.is_on, seed=3
    )
    cfg = ClimateConfig(poll_interval_s=30.0, **climate_kw)
    svc = ClimateService(cfg, clock, Bus(), sensor, fan)
    return clock, fan, sensor, svc


async def test_ventilator_stvarno_hladi_prostoriju():
    """Zatvorena petlja: bez nje termostat nikad nije stvarno testiran."""
    clock, fan, sensor, _ = build()
    await fan.set(True)
    start = sensor.room_c
    for _ in range(60):
        clock.advance(60.0)
        await sensor.read()
    assert sensor.room_c < start - 2.0


async def test_ventilator_mijenja_ishod():
    """Ista prostorija, isto vrijeme, jedina razlika je ventilator."""
    async def run(fan_on: bool) -> float:
        clock, fan, sensor, _ = build()
        await fan.set(fan_on)
        for _ in range(60):
            clock.advance(60.0)
            await sensor.read()
        return sensor.room_c

    assert await run(True) < await run(False) - 3.0


async def test_kvar_senzora_ne_rusi_servis():
    clock, fan, sensor, svc = build()
    sensor.fault.error = True
    for _ in range(5):
        await svc._tick()          # ne smije baciti
        clock.advance(30.0)
    assert svc.error_count == 5
    assert fan.is_on is True       # fail-safe


async def test_zamrznut_senzor_okida_watchdog():
    clock, fan, sensor, svc = build(stale_after_s=300.0)
    await svc._tick()
    sensor.fault.freeze = True
    for _ in range(20):            # 10 minuta zamrznutog ocitanja
        clock.advance(30.0)
        await svc._tick()
    assert fan.is_on is True
    assert svc.last_decision.healthy is False


async def test_besmislena_vrijednost_se_odbacuje():
    clock, fan, sensor, svc = build()
    sensor.fault.garbage = True
    clock.advance(30.0)
    await svc._tick()
    assert svc.last_decision.healthy is False
    assert fan.is_on is True


async def test_dogadaj_ocitanja_ide_na_bus():
    clock, fan, sensor, svc = build()
    q = svc._bus.subscribe()
    await svc._tick()
    msg = q.get_nowait()
    assert msg["type"] == EV_READING
    assert "temperature_c" in msg["data"]


async def test_rucni_nacin_ignorira_temperaturu():
    clock, fan, sensor, svc = build()
    await svc.set_mode(FanMode.OFF)
    for _ in range(40):
        clock.advance(60.0)
        await svc._tick()
    assert fan.is_on is False


class _DummyAudio:
    def __init__(self):
        self.order: list[str] = []

    async def play_file(self, path): self.order.append(str(path))
    async def say(self, text): self.order.append(text)
    async def stop(self): pass
    async def close(self): pass


async def test_alarm_preskace_red():
    from rpictl.models import Priority

    audio = _DummyAudio()
    svc = AnnouncerService(ManualClock(), Bus(), audio)
    svc.enqueue("prva")
    svc.enqueue("druga")
    svc.enqueue("POZAR", priority=Priority.ALARM)

    task = asyncio.create_task(svc.run())
    await asyncio.sleep(0.05)
    task.cancel()
    assert audio.order[0] == "POZAR"
    assert audio.order[1:] == ["prva", "druga"]


class _TrackingMusic(FakeMusicPlayer):
    """FakeMusicPlayer koji bilježi redoslijed poziva, za provjeru ducking-a."""

    def __init__(self):
        super().__init__()
        self.calls: list[str] = []

    async def play(self, track=None):
        self.calls.append("play")
        await super().play(track)

    async def pause(self):
        self.calls.append("pause")
        await super().pause()

    async def resume(self):
        self.calls.append("resume")
        await super().resume()


async def test_najava_pauzira_i_nastavlja_glazbu():
    bus = Bus()
    music_hal = _TrackingMusic()
    music_svc = MusicService(ManualClock(), bus, music_hal)
    announcer = AnnouncerService(ManualClock(), bus, _DummyAudio())

    await music_svc.play()
    announcer.enqueue("najava")

    tasks = [asyncio.create_task(music_svc.run()), asyncio.create_task(announcer.run())]
    await asyncio.sleep(0.05)
    for t in tasks:
        t.cancel()

    assert music_hal.calls == ["play", "pause", "resume"]
    assert music_hal.is_playing is True


async def test_glazba_se_ne_nastavlja_ako_nije_svirala():
    bus = Bus()
    music_hal = _TrackingMusic()
    music_svc = MusicService(ManualClock(), bus, music_hal)
    announcer = AnnouncerService(ManualClock(), bus, _DummyAudio())

    announcer.enqueue("najava")

    tasks = [asyncio.create_task(music_svc.run()), asyncio.create_task(announcer.run())]
    await asyncio.sleep(0.05)
    for t in tasks:
        t.cancel()

    assert music_hal.calls == []
    assert music_hal.is_playing is False
