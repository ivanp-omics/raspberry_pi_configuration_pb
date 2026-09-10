"""Konfiguracija iz YAML-a, validirana pydanticom.

Jedno mjesto koje zna sto je gdje podeseno. Ako polje fali, program pada
odmah pri pokretanju s jasnom porukom - a ne u tri ujutro kad zatreba.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    # None = bez provjere (lokalni rad, simulacija, Tailscale-only pristup).
    # Postavi kad API treba biti dohvatljiv i izvan tailneta (npr. preko
    # Tailscale Funnela za WordPress bridge) - tad postaje jedina brava.
    api_token: str | None = None


class ClimateConfig(BaseModel):
    poll_interval_s: float = 30.0
    temp_on_c: float = 26.0
    temp_off_c: float = 24.0
    min_on_s: float = 180.0
    min_off_s: float = 180.0
    stale_after_s: float = 300.0
    valid_min_c: float = -20.0
    valid_max_c: float = 80.0

    @model_validator(mode="after")
    def _check_hysteresis(self) -> "ClimateConfig":
        if self.temp_off_c >= self.temp_on_c:
            raise ValueError(
                "temp_off_c mora biti manji od temp_on_c, inace nema histereze "
                "i ventilator ce ciklati"
            )
        return self


class SensorSimConfig(BaseModel):
    start_c: float = 23.0
    outdoor_mean_c: float = 21.0
    outdoor_amp_c: float = 6.0
    k_env: float = 0.020
    solar_gain_c: float = 0.030
    fan_cooling_c: float = 0.110
    noise_c: float = 0.15


class SensorConfig(BaseModel):
    i2c_address: int = 0x76
    sim: SensorSimConfig = Field(default_factory=SensorSimConfig)


class FanConfig(BaseModel):
    gpio_pin: int = 17
    relay_active_high: bool = False
    fan_runs_when_energised: bool = False


class AudioConfig(BaseModel):
    media_dir: str = "media"
    player_cmd: list[str] = Field(default_factory=lambda: ["aplay", "-q"])
    tts_cmd: list[str] = Field(default_factory=lambda: ["espeak-ng", "-v", "hr"])
    sim_speak_rate_wps: float = 2.5


class MusicConfig(BaseModel):
    media_dir: str = "media/music"
    player_cmd: list[str] = Field(
        default_factory=lambda: ["mpv", "--no-video", "--idle=yes", "--really-quiet"]
    )
    ipc_socket: str = "/tmp/rpictl-mpv.sock"


class NetworkConfig(BaseModel):
    scan_interval_s: float = 300.0
    subnet: str = "192.168.1.0/24"
    method: Literal["arp", "nmap"] = "arp"


class TelemetryConfig(BaseModel):
    db_path: str = "data/rpictl.sqlite"
    retention_days: int = 30


class Config(BaseModel):
    simulate: bool = True
    sim_speed: float = 60.0
    server: ServerConfig = Field(default_factory=ServerConfig)
    climate: ClimateConfig = Field(default_factory=ClimateConfig)
    sensor: SensorConfig = Field(default_factory=SensorConfig)
    fan: FanConfig = Field(default_factory=FanConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    music: MusicConfig = Field(default_factory=MusicConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)

    @model_validator(mode="after")
    def _no_time_travel_on_hardware(self) -> "Config":
        if not self.simulate and self.sim_speed != 1.0:
            raise ValueError("sa stvarnim hardverom sim_speed mora biti 1.0")
        return self


def load_config(path: str | Path = "config.yaml") -> Config:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"nema konfiguracije: {p.resolve()}")
    with p.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return Config.model_validate(raw)
