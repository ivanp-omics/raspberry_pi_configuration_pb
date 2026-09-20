"""Slusanje prostorije (prekidac), radio preseti i glasnoca.

Tezina je na tome da slusanje ima STANJE izmedu dva poziva: start otvara
sesiju, stop je zatvara i vraca snimku. Tu se lako uvuku greske - zaostala
brava, snimka koja se ne vrati, druga sesija preko prve - pa se svaka od tih
situacija ovdje provjerava.
"""

from __future__ import annotations

import io
import time
import wave

import pytest
import yaml
from fastapi.testclient import TestClient

from rpictl.app import create_app


def _config(tmp_path, **extra) -> str:
    cfg = {
        "simulate": True,
        "sim_speed": 60.0,
        "server": {"host": "127.0.0.1", "port": 8000},
        "audio": {"media_dir": str(tmp_path / "media")},
        "music": {"media_dir": str(tmp_path / "media" / "music")},
        "telemetry": {"db_path": str(tmp_path / "test.sqlite")},
    }
    cfg.update(extra)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return str(path)


def _trajanje(wav: bytes) -> float:
    with wave.open(io.BytesIO(wav), "rb") as fh:
        return fh.getnframes() / fh.getframerate()


def test_start_pa_stop_vraca_svirljivu_snimku(tmp_path):
    app = create_app(_config(tmp_path))
    with TestClient(app) as c:
        r = c.post("/api/listen/start")
        assert r.status_code == 200
        assert r.json()["recording"] is True

        # sim_speed=60: 0.05 s stvarnog vremena = ~3 simulirane sekunde
        time.sleep(0.05)

        r2 = c.post("/api/listen/stop")
        assert r2.status_code == 200
        assert r2.headers["content-type"].startswith("audio/")
        # Lazni snimac vraca stvarni WAV - da se vidi da front dobiva nesto
        # sto browser moze pustiti.
        assert _trajanje(r2.content) > 0.5


def test_duljina_snimke_prati_trajanje_sesije(tmp_path):
    """Duze drzanje prekidaca = duza snimka."""
    app = create_app(_config(tmp_path))
    with TestClient(app) as c:
        c.post("/api/listen/start")
        time.sleep(0.03)
        kratka = _trajanje(c.post("/api/listen/stop").content)

        c.post("/api/listen/start")
        time.sleep(0.12)
        duga = _trajanje(c.post("/api/listen/stop").content)

    assert duga > kratka


def test_druga_sesija_dobiva_409(tmp_path):
    """Mikrofon je jedan: drugi start mora dobiti jasnu poruku."""
    app = create_app(_config(tmp_path))
    with TestClient(app) as c:
        assert c.post("/api/listen/start").status_code == 200
        assert c.post("/api/listen/start").status_code == 409
        c.post("/api/listen/stop")


def test_stop_bez_starta_dobiva_409(tmp_path):
    app = create_app(_config(tmp_path))
    with TestClient(app) as c:
        assert c.post("/api/listen/stop").status_code == 409


def test_brava_se_oslobodi_nakon_stopa(tmp_path):
    """Nakon uredne sesije mora se moci odmah pokrenuti nova."""
    app = create_app(_config(tmp_path))
    with TestClient(app) as c:
        c.post("/api/listen/start")
        c.post("/api/listen/stop")
        assert c.post("/api/listen/start").status_code == 200
        c.post("/api/listen/stop")


def test_status_prati_slusanje(tmp_path):
    app = create_app(_config(tmp_path))
    with TestClient(app) as c:
        prije = c.get("/api/status").json()["listen"]
        assert prije["recording"] is False
        assert prije["max_seconds"] == 60.0
        assert prije["mime"].startswith("audio/")

        c.post("/api/listen/start")
        tijekom = c.get("/api/status").json()["listen"]
        assert tijekom["recording"] is True

        c.post("/api/listen/stop")
        assert c.get("/api/status").json()["listen"]["recording"] is False


def test_granica_trajanja_iz_konfiguracije(tmp_path):
    app = create_app(_config(tmp_path, listen={"max_seconds": 25.0}))
    with TestClient(app) as c:
        assert c.get("/api/status").json()["listen"]["max_seconds"] == 25.0


@pytest.mark.parametrize("nevaljano", [0.5, 601.0])
def test_odbija_besmislenu_granicu(tmp_path, nevaljano):
    """Zastita da netko ne upise 0.1 s ili pola dana u config.local.yaml."""
    from pydantic import ValidationError

    from rpictl.config import load_config

    with pytest.raises(ValidationError):
        load_config(_config(tmp_path, listen={"max_seconds": nevaljano}))


# --------------------------------------------------------------------------
# Snimka najave (odvojeno od slusanja - ovo je glas iz preglednika)
# --------------------------------------------------------------------------

def test_snimka_najave_ide_jednim_pozivom(tmp_path):
    """Sirovo tijelo + nastavak: spremi i najavi bez multiparta i bez dva poziva."""
    app = create_app(_config(tmp_path))
    with TestClient(app) as c:
        r = c.post(
            "/api/announce/clip?ext=webm",
            content=b"fake webm payload",
            headers={"Content-Type": "audio/webm"},
        )
        assert r.status_code == 200
        assert r.json()["saved"] == "snimka-razglas.webm"
        assert r.json()["pending"] >= 1

        # Ime odreduje server i rotira - druga snimka ne pravi novu datoteku.
        c.post("/api/announce/clip?ext=webm", content=b"druga snimka")
        imena = [f["name"] for f in c.get("/api/media/announce").json()["files"]]
        assert imena.count("snimka-razglas.webm") == 1


def test_snimka_najave_odbija_nedopusten_nastavak(tmp_path):
    app = create_app(_config(tmp_path))
    with TestClient(app) as c:
        assert c.post("/api/announce/clip?ext=sh", content=b"#!/bin/sh").status_code == 422


# --------------------------------------------------------------------------
# Radio preseti i glasnoca
# --------------------------------------------------------------------------

def test_glasnoca_glazbe(tmp_path):
    app = create_app(_config(tmp_path))
    with TestClient(app) as c:
        assert c.get("/api/status").json()["music"]["volume"] == 40

        assert c.post("/api/music/volume", json={"volume": 75}).json()["volume"] == 75
        assert c.get("/api/status").json()["music"]["volume"] == 75

        # Granice cuva pydantic, da klizac ne posalje besmislicu.
        assert c.post("/api/music/volume", json={"volume": 101}).status_code == 422
        assert c.post("/api/music/volume", json={"volume": -1}).status_code == 422
        assert c.get("/api/status").json()["music"]["volume"] == 75


def test_pocetna_glasnoca_iz_konfiguracije(tmp_path):
    app = create_app(
        _config(tmp_path, music={
            "media_dir": str(tmp_path / "media" / "music"),
            "volume": 15,
        })
    )
    with TestClient(app) as c:
        assert c.get("/api/status").json()["music"]["volume"] == 15


def test_status_objavljuje_postaje(tmp_path):
    app = create_app(_config(tmp_path))
    with TestClient(app) as c:
        postaje = c.get("/api/status").json()["stations"]
        assert postaje, "ocekujemo barem jedan preset iz defaulta"
        for p in postaje:
            assert p["name"]
            assert p["url"].startswith("http")


def test_postaje_se_mogu_pregaziti_konfiguracijom(tmp_path):
    app = create_app(
        _config(tmp_path, music={
            "media_dir": str(tmp_path / "media" / "music"),
            "stations": [{"name": "Samo jedna", "url": "https://example.test/stream"}],
        })
    )
    with TestClient(app) as c:
        assert c.get("/api/status").json()["stations"] == [
            {"name": "Samo jedna", "url": "https://example.test/stream"}
        ]
