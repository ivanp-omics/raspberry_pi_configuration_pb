"""Jedino mjesto u projektu koje zna je li simulacija ili pravi hardver.

Nigdje drugdje ne smije stajati `if config.simulate`. Ako se pojavi, znaci
da je apstrakcija negdje procurila.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..clock import Clock
from ..config import Config
from .base import (
    AudioPlayer,
    FanControl,
    MusicPlayer,
    NetworkScanner,
    TemperatureSensor,
)

log = logging.getLogger(__name__)


@dataclass
class Hal:
    sensor: TemperatureSensor
    fan: FanControl
    audio: AudioPlayer
    music: MusicPlayer
    scanner: NetworkScanner
    simulated: bool

    async def close(self) -> None:
        for dev in (self.sensor, self.audio, self.music, self.scanner, self.fan):
            try:
                await dev.close()
            except Exception:  # noqa: BLE001 - gasenje ne smije pasti
                log.exception("greska pri zatvaranju %s", type(dev).__name__)


def build_hal(cfg: Config, clock: Clock) -> Hal:
    if cfg.simulate:
        from .audio_fake import FakeAudioPlayer
        from .music_fake import FakeMusicPlayer
        from .netscan_fake import FakeNetworkScanner
        from .relay_fake import FakeFan
        from .sensor_fake import FakeTemperatureSensor

        fan = FakeFan(clock)
        # Senzor mora znati stanje ventilatora - bez toga je petlja otvorena
        # i termostat se zapravo ne testira.
        sensor = FakeTemperatureSensor(clock, cfg.sensor.sim, fan_state=lambda: fan.is_on)
        log.info("HAL: simulacija (sim_speed=%.1f)", cfg.sim_speed)
        return Hal(
            sensor=sensor,
            fan=fan,
            audio=FakeAudioPlayer(clock, cfg.audio.sim_speak_rate_wps),
            music=FakeMusicPlayer(),
            scanner=FakeNetworkScanner(),
            simulated=True,
        )

    from .audio_alsa import AlsaAudioPlayer
    from .music_mpv import MpvMusicPlayer
    from .netscan_arp import ArpNetworkScanner
    from .relay_gpio import GpioRelayFan
    from .sensor_bme680 import Bme680Sensor

    log.info("HAL: pravi hardver")
    return Hal(
        sensor=Bme680Sensor(clock, cfg.sensor.i2c_address),
        fan=GpioRelayFan(clock, cfg.fan),
        audio=AlsaAudioPlayer(cfg.audio),
        music=MpvMusicPlayer(cfg.music),
        scanner=ArpNetworkScanner(cfg.network),
        simulated=False,
    )
