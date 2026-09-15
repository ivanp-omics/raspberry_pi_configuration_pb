"""Testovi datoteka za razglas i glazbu.

Tezina je na imenu datoteke: ono jedino stize izvana, a pathlib ima zamku u
kojoj apsolutna putanja pregazi cijelu bazu ("media" / "/etc/shadow" daje
"/etc/shadow"). Zato se provjerava da nista ne izade iz svoje mape.
"""

from __future__ import annotations

import pytest
import yaml
from fastapi.testclient import TestClient

from rpictl.app import create_app
from rpictl.hal.music_mpv import is_stream
from rpictl.media import MediaError, MediaLibrary


@pytest.fixture
def lib(tmp_path) -> MediaLibrary:
    return MediaLibrary(str(tmp_path / "media"), str(tmp_path / "media" / "music"))


def test_sprema_i_izlistava(lib):
    lib.save("announce", "zvono.wav", b"RIFF fake")
    assert [f["name"] for f in lib.list("announce")] == ["zvono.wav"]
    assert lib.list("music") == []


def test_putanja_u_imenu_se_reze(lib, tmp_path):
    lib.save("announce", "../../../../etc/zlo.wav", b"x")
    # Ostaje samo ime, datoteka je u svojoj mapi i nigdje drugdje.
    assert [f["name"] for f in lib.list("announce")] == ["zlo.wav"]
    assert (tmp_path / "media" / "zlo.wav").is_file()


def test_apsolutna_putanja_ne_izlazi_iz_mape(lib, tmp_path):
    lib.save("music", "/etc/shadow.mp3", b"x")
    assert (tmp_path / "media" / "music" / "shadow.mp3").is_file()


def test_odbija_nedopusten_nastavak(lib):
    with pytest.raises(MediaError):
        lib.save("announce", "skripta.sh", b"x")
    # aplay cita samo WAV - mp3 za najavu ne prolazi, iako prolazi za glazbu.
    with pytest.raises(MediaError):
        lib.save("announce", "pjesma.mp3", b"x")
    assert lib.save("music", "pjesma.mp3", b"x") == "pjesma.mp3"


def test_odbija_prazno_i_cudno_ime(lib):
    with pytest.raises(MediaError):
        lib.save("announce", "zvono.wav", b"")
    with pytest.raises(MediaError):
        lib.save("announce", "zvo\nno.wav", b"x")


def test_brisanje(lib):
    lib.save("music", "pjesma.mp3", b"x")
    lib.delete("music", "pjesma.mp3")
    assert lib.list("music") == []
    with pytest.raises(MediaError):
        lib.delete("music", "nema-me.mp3")


def test_nepoznata_vrsta(lib):
    with pytest.raises(MediaError):
        lib.list("cudo")


def test_prepoznaje_stream():
    assert is_stream("https://ice1.somafm.com/groovesalad-128-mp3")
    assert is_stream("http://stream.example/radio")
    assert not is_stream("pjesma.mp3")
    assert not is_stream("/etc/shadow")


def _config(tmp_path) -> str:
    cfg = {
        "simulate": True,
        "sim_speed": 60.0,
        "server": {"host": "127.0.0.1", "port": 8000},
        "audio": {"media_dir": str(tmp_path / "media")},
        "music": {"media_dir": str(tmp_path / "media" / "music")},
        "telemetry": {"db_path": str(tmp_path / "test.sqlite")},
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return str(path)


def test_upload_preko_apija(tmp_path):
    app = create_app(_config(tmp_path))
    with TestClient(app) as c:
        r = c.post(
            "/api/media/announce",
            files={"file": ("najava.wav", b"RIFF fake", "audio/wav")},
        )
        assert r.status_code == 200
        assert r.json()["saved"] == "najava.wav"

        assert [f["name"] for f in c.get("/api/media/announce").json()["files"]] == [
            "najava.wav"
        ]

        assert c.delete("/api/media/announce/najava.wav").status_code == 200
        assert c.get("/api/media/announce").json()["files"] == []


def test_upload_odbija_nedopusten_tip(tmp_path):
    app = create_app(_config(tmp_path))
    with TestClient(app) as c:
        r = c.post(
            "/api/media/announce",
            files={"file": ("zlo.sh", b"#!/bin/sh", "text/plain")},
        )
        assert r.status_code == 422
