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
    temp_on_c: float = 35.0
    temp_off_c: float = 32.0
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
    # mpv, a ne aplay: aplay cita samo WAV/PCM, a snimke iz browsera dolaze kao
    # webm/ogg (MediaRecorder ne zna u WAV). mpv svira i jedno i drugo, pa nema
    # potrebe za pretvaranjem formata na Pi-ju.
    player_cmd: list[str] = Field(
        default_factory=lambda: ["mpv", "--no-video", "--really-quiet"]
    )
    tts_cmd: list[str] = Field(default_factory=lambda: ["espeak-ng", "-v", "hr"])
    sim_speak_rate_wps: float = 2.5


class RadioStation(BaseModel):
    name: str
    url: str


class MusicConfig(BaseModel):
    media_dir: str = "media/music"
    player_cmd: list[str] = Field(
        default_factory=lambda: ["mpv", "--no-video", "--idle=yes", "--really-quiet"]
    )
    ipc_socket: str = "/tmp/rpictl-mpv.sock"
    # Pocetna glasnoca glazbe. Namjerno ovdje, a ne kao --volume u player_cmd:
    # sucelje je mijenja uzivo preko IPC-a, pa mora postojati jedno mjesto koje
    # zna trenutnu vrijednost i vrati je ako se mpv proces ponovno pokrene.
    volume: int = Field(default=40, ge=0, le=100)
    # Preseti za gumbe u sucelju. .pls umjesto direktnog ice3/ice5 linka je
    # namjerno: playlista sadrzi vise rezervnih servera pa mpv sam preskoci
    # onaj koji ne radi, a SomaFM direktne hostove s vremenom mijenja.
    stations: list[RadioStation] = Field(
        default_factory=lambda: [
            RadioStation(name="Groove Salad", url="https://somafm.com/groovesalad.pls"),
            RadioStation(name="Beat Blender", url="https://somafm.com/beatblender.pls"),
            RadioStation(name="PopTron", url="https://somafm.com/poptron.pls"),
            RadioStation(name="Boot Liquor", url="https://somafm.com/bootliquor.pls"),
            RadioStation(name="Radio Paradise", url="http://stream.radioparadise.com/mp3-192"),
        ]
    )


class NetworkConfig(BaseModel):
    scan_interval_s: float = 300.0
    subnet: str = "192.168.1.0/24"
    method: Literal["arp", "nmap"] = "arp"


class TelemetryConfig(BaseModel):
    db_path: str = "data/rpictl.sqlite"
    retention_days: int = 30


class ListenConfig(BaseModel):
    """Snimanje kratkog isjecka prostorije ("sto se tamo dogada")."""

    # Trajanje je fiksno i podesivo ovdje, a ne parametar iz zahtjeva: mikrofon
    # je jedan, pa dugacko snimanje po tudjem zahtjevu blokira i uredaj i
    # jednog radnika na serveru.
    clip_seconds: float = Field(default=10.0, ge=1.0, le=60.0)
    # plughw:, a ne hw: - "hw" je sirovi uredaj i trazi tocno one parametre
    # koje cip podrzava, pa jeftina USB kartica s mono ulazom odbije ffmpegov
    # zadani stereo ("cannot set channel count to 2"). "plughw" ubacuje ALSA
    # konverzijski sloj koji to posreduje, isto kao sto `arecord default` radi.
    device: str = "plughw:0"
    record_cmd: list[str] = Field(
        default_factory=lambda: ["ffmpeg", "-nostdin", "-loglevel", "error"]
    )
    # Idu PRIJE -i, pa vrijede za otvaranje uredaja (za razliku od codec_args
    # ispod, koji vrijede za kodiranje). Na spremistu plughw svejedno otvori
    # stereo i sam posreduje, pa je ovo samo nagovjestaj za uredaje koji ga
    # postuju - ne oslanjaj se na njega, "plughw" je ono sto stvarno rjesava.
    input_args: list[str] = Field(default_factory=lambda: ["-ac", "1"])
    # Opus/Ogg jer je 10 s ~30 kB umjesto ~900 kB (WAV) - bitno kad isjecak
    # putuje kroz WordPress proxy. Ako ffmpeg na uredaju nema libopus, ovdje
    # se prebaci na: ["-ac", "1", "-c:a", "pcm_s16le"] + container "wav" +
    # mime "audio/wav", bez ikakve izmjene koda.
    codec_args: list[str] = Field(
        default_factory=lambda: ["-ac", "1", "-c:a", "libopus", "-b:a", "24k"]
    )
    container: str = "ogg"
    mime: str = "audio/ogg"


class Config(BaseModel):
    simulate: bool = True
    sim_speed: float = 60.0
    server: ServerConfig = Field(default_factory=ServerConfig)
    climate: ClimateConfig = Field(default_factory=ClimateConfig)
    sensor: SensorConfig = Field(default_factory=SensorConfig)
    fan: FanConfig = Field(default_factory=FanConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    music: MusicConfig = Field(default_factory=MusicConfig)
    listen: ListenConfig = Field(default_factory=ListenConfig)
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
