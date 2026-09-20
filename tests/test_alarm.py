"""Alarm i zdravlje uredaja.

Alarm se razlikuje od obicne najave po dvije stvari: preskace red (to je vec
radio prioritet) i PREKIDA ono sto trenutno svira (to je novo). Druga tocka se
lako izgubi pri refaktoriranju, pa se ovdje mjeri stvarnim redoslijedom
dogadaja, a ne samo time da poziv ne pukne.
"""

from __future__ import annotations

import asyncio

import pytest

from rpictl.bus import Bus
from rpictl.clock import ScaledClock
from rpictl.hal.audio_fake import FakeAudioPlayer
from rpictl.models import Priority
from rpictl.services.announcer import AnnouncerService
from rpictl.system import cpu_temperature_c

# speed=4, ne uobicajenih 60: pri 60 bi najava od 4 simulirane sekunde trajala
# 0.067 stvarnih i zavrsila prije nego je test stigne pogledati. Ovako traje
# oko sekunde - dovoljno da se uhvati "usred sviranja", a testovi su i dalje brzi.
SPEED = 4.0


def _servis() -> tuple[AnnouncerService, FakeAudioPlayer, Bus]:
    clock = ScaledClock(speed=SPEED)
    bus = Bus()
    audio = FakeAudioPlayer(clock, speak_rate_wps=2.5)
    return AnnouncerService(clock, bus, audio), audio, bus


async def test_alarm_prekida_najavu_koja_svira():
    servis, _, _ = _servis()
    task = asyncio.create_task(servis.run())
    try:
        servis.enqueue(text="duga najava koja traje i traje i traje i traje")
        await asyncio.sleep(0.1)
        assert servis.current is not None, "prva najava mora krenuti"
        prva = servis.current.id

        servis.enqueue(path="alarm.wav", priority=Priority.ALARM)
        await asyncio.sleep(0.25)

        # Prva je presjecena, alarm je preuzeo razglas.
        assert servis.current is not None
        assert servis.current.id != prva
        assert servis.current.path == "alarm.wav"
    finally:
        task.cancel()


async def test_obicna_najava_ne_prekida():
    """Samo alarm smije presjeci - inace bi svaka najava gazila prethodnu."""
    servis, _, _ = _servis()
    task = asyncio.create_task(servis.run())
    try:
        servis.enqueue(text="prva najava koja traje dovoljno dugo")
        await asyncio.sleep(0.1)
        prva = servis.current.id

        servis.enqueue(text="druga")
        await asyncio.sleep(0.25)

        assert servis.current is not None
        assert servis.current.id == prva, "prva mora dovrsiti svoje"
    finally:
        task.cancel()


async def test_alarm_u_prazan_red_samo_svira():
    """Prekidanje ne smije puknuti kad nema sto prekinuti."""
    servis, _, _ = _servis()
    task = asyncio.create_task(servis.run())
    try:
        servis.enqueue(path="alarm.wav", priority=Priority.ALARM)
        await asyncio.sleep(0.2)
        assert servis.current is not None
        assert servis.current.path == "alarm.wav"
    finally:
        task.cancel()


async def test_gong_ide_prije_sadrzaja():
    """Gong pa tek onda najava - i to jednim putem, za sve izvore najave."""
    clock = ScaledClock(speed=SPEED)
    audio = FakeAudioPlayer(clock, speak_rate_wps=2.5)
    servis = AnnouncerService(clock, Bus(), audio, chime="dingdong.wav")
    task = asyncio.create_task(servis.run())
    try:
        # Tekst mora biti dovoljno dug da se stigne uhvatiti usred govora:
        # gong traje 4 simulirane sekunde, pa tek onda krece sadrzaj.
        servis.enqueue(text="proba jedan dva tri cetiri pet sest sedam osam devet")
        await asyncio.sleep(0.1)
        assert "dingdong.wav" in (audio.now_playing or ""), "prvo mora ici gong"
        await asyncio.sleep(1.2)
        assert "proba" in (audio.now_playing or ""), "pa tek onda sadrzaj"
    finally:
        task.cancel()


async def test_gong_ne_ide_ispred_samog_sebe():
    """Klik na Ding dong ne smije dati dva gonga."""
    clock = ScaledClock(speed=SPEED)
    audio = FakeAudioPlayer(clock, speak_rate_wps=2.5)
    servis = AnnouncerService(clock, Bus(), audio, chime="dingdong.wav")
    task = asyncio.create_task(servis.run())
    try:
        servis.enqueue(path="dingdong.wav")
        await asyncio.sleep(0.1)
        assert audio.play_count == 1, "samo jedno pustanje, ne gong + gong"
    finally:
        task.cancel()


# --------------------------------------------------------------------------
# Alarm kao prekidac
# --------------------------------------------------------------------------

def _alarm(max_seconds: float = 60.0):
    from rpictl.config import AlarmConfig
    from rpictl.services.alarm import AlarmService

    clock = ScaledClock(speed=SPEED)
    bus = Bus()
    audio = FakeAudioPlayer(clock, speak_rate_wps=2.5)
    cfg = AlarmConfig(file="alarm.wav", max_seconds=max_seconds)
    return AlarmService(cfg, clock, bus, audio), audio, clock


async def test_alarm_svira_u_petlji_dok_se_ne_ugasi():
    alarm, audio, _ = _alarm()
    assert not alarm.active

    await alarm.start()
    assert alarm.active
    assert audio.looping, "alarm mora vrtjeti zvuk u petlji, ne jednokratno"

    await alarm.stop()
    assert not alarm.active
    assert not audio.looping


async def test_alarm_se_sam_gasi_nakon_granice():
    # 2 simulirane sekunde pri speed=4 su pola stvarne.
    alarm, audio, _ = _alarm(max_seconds=2.0)
    await alarm.start()
    assert alarm.active

    await asyncio.sleep(0.9)
    assert not alarm.active, "serverski tajmer mora ugasiti alarm"
    assert not audio.looping


async def test_najave_cekaju_dok_alarm_svira():
    """Najava se ne gubi, samo ceka - inace bi se borila za zvucni uredaj."""
    alarm, audio, clock = _alarm()
    servis = AnnouncerService(clock, Bus(), audio, gate=alarm.idle)
    task = asyncio.create_task(servis.run())
    try:
        await alarm.start()
        servis.enqueue(text="ovo mora pricekati")
        await asyncio.sleep(0.2)
        assert servis.current is None, "najava ne smije krenuti dok alarm svira"
        assert servis.pending == 0, "ali je uzeta iz reda i ceka na vratima"

        await alarm.stop()
        await asyncio.sleep(0.2)
        assert servis.current is not None, "nakon alarma najava mora krenuti"
    finally:
        task.cancel()


def test_temperatura_pija_ne_puca_bez_sysfsa():
    """Na Windowsu/Macu datoteke nema - mora vratiti None, ne iznimku."""
    vrijednost = cpu_temperature_c()
    assert vrijednost is None or isinstance(vrijednost, float)


def test_temperatura_pija_cita_tisucinke(tmp_path, monkeypatch):
    lazni = tmp_path / "temp"
    lazni.write_text("48312\n", encoding="ascii")
    monkeypatch.setattr("rpictl.system.THERMAL_FILE", lazni)
    assert cpu_temperature_c() == 48.3


def test_temperatura_pija_kod_smeca_vraca_none(tmp_path, monkeypatch):
    lazni = tmp_path / "temp"
    lazni.write_text("nije broj", encoding="ascii")
    monkeypatch.setattr("rpictl.system.THERMAL_FILE", lazni)
    assert cpu_temperature_c() is None


@pytest.mark.parametrize("kljuc", ["cpu_temp_c", "warn_c", "throttle_c"])
def test_status_objavljuje_zdravlje_uredaja(tmp_path, kljuc):
    """Front crta ovo, pa oblik mora biti stabilan."""
    import yaml
    from fastapi.testclient import TestClient

    from rpictl.app import create_app

    cfg = {
        "simulate": True,
        "sim_speed": 60.0,
        "server": {"host": "127.0.0.1", "port": 8000},
        "audio": {"media_dir": str(tmp_path / "media")},
        "music": {"media_dir": str(tmp_path / "media" / "music")},
        "telemetry": {"db_path": str(tmp_path / "t.sqlite")},
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    with TestClient(create_app(str(path))) as c:
        assert kljuc in c.get("/api/status").json()["system"]


async def test_status_kaze_da_najava_ceka_alarm():
    """Dok ceka pred vratima najava nije "playing" - inace sucelje laze."""
    alarm, audio, clock = _alarm()
    servis = AnnouncerService(clock, Bus(), audio, gate=alarm.idle)
    task = asyncio.create_task(servis.run())
    try:
        await alarm.start()
        servis.enqueue(text="ova ceka")
        await asyncio.sleep(0.2)

        snap = servis.snapshot()
        assert snap["waiting"] is True
        assert snap["playing"] is None, "ne smije tvrditi da nesto svira"

        await alarm.stop()
        await asyncio.sleep(0.2)
        snap = servis.snapshot()
        assert snap["waiting"] is False
        assert snap["playing"] is not None
    finally:
        task.cancel()


async def test_alarm_presjekom_gonga_ne_pusta_sadrzaj_preko_alarma():
    """Alarm prekine gong - sadrzaj NE smije krenuti dok alarm svira."""
    alarm, audio, clock = _alarm()
    servis = AnnouncerService(clock, Bus(), audio, chime="dingdong.wav", gate=alarm.idle)
    task = asyncio.create_task(servis.run())
    try:
        servis.enqueue(text="sadrzaj koji ne smije preko alarma")
        await asyncio.sleep(0.1)
        assert "dingdong.wav" in (audio.now_playing or "")

        await alarm.start()
        await asyncio.sleep(0.3)
        assert audio.looping, "alarm mora svirati"
        assert servis.snapshot()["waiting"] is True, "sadrzaj mora cekati, ne ici preko"
    finally:
        task.cancel()
