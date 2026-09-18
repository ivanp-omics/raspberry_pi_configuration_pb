"""Testovi snimanja isjecka prostorije i presetov iz konfiguracije.

Tezina je na tome da trajanje i popis postaja dolaze IZ KONFIGURACIJE, a ne iz
zahtjeva ili frontenda - to je ono sto sprjecava da se popis razide izmedu
index.html i WordPress plugina, i da netko zahtjevom naruci deset minuta
snimanja na uredaju koji ima jedan mikrofon.
"""

from __future__ import annotations

import asyncio
import io
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
        # Kratko, da testovi ne traju stvarnih deset sekundi.
        "listen": {"clip_seconds": 1.0},
    }
    cfg.update(extra)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return str(path)


def test_vraca_svirljiv_isjecak(tmp_path):
    app = create_app(_config(tmp_path))
    with TestClient(app) as c:
        r = c.post("/api/listen")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("audio/")

        # Lazni snimac vraca stvarni WAV - ako se ovo ne da otvoriti, front
        # bi dobio nesto sto browser ne moze pustiti.
        with wave.open(io.BytesIO(r.content), "rb") as fh:
            trajanje = fh.getnframes() / fh.getframerate()
        assert 0.9 <= trajanje <= 1.1


def test_trajanje_dolazi_iz_konfiguracije(tmp_path):
    app = create_app(_config(tmp_path, listen={"clip_seconds": 2.0}))
    with TestClient(app) as c:
        with wave.open(io.BytesIO(c.post("/api/listen").content), "rb") as fh:
            trajanje = fh.getnframes() / fh.getframerate()
        assert 1.9 <= trajanje <= 2.1


def test_status_objavljuje_postaje_i_trajanje(tmp_path):
    app = create_app(_config(tmp_path))
    with TestClient(app) as c:
        s = c.get("/api/status").json()

        # Front crta gumbe iz ovoga, pa oblik mora biti stabilan.
        assert s["listen"]["clip_seconds"] == 1.0
        assert s["listen"]["mime"].startswith("audio/")
        assert s["stations"], "ocekujemo barem jedan preset iz defaulta"
        for postaja in s["stations"]:
            assert postaja["name"]
            assert postaja["url"].startswith("http")


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


def test_prazan_zahtjev_ne_treba_tijelo(tmp_path):
    """POST bez tijela mora proci - front ne salje nista, trajanje je iz configa."""
    app = create_app(_config(tmp_path))
    with TestClient(app) as c:
        assert c.post("/api/listen").status_code == 200


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
        r = c.post("/api/announce/clip?ext=sh", content=b"#!/bin/sh")
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_drugo_snimanje_dobiva_409(tmp_path):
    """Mikrofon je jedan: drugi zahtjev mora dobiti jasnu poruku, ne pokvarenu snimku."""
    import httpx

    app = create_app(_config(tmp_path, listen={"clip_seconds": 3.0}))
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://test") as c,
    ):
        prvi = asyncio.create_task(c.post("/api/listen"))
        await asyncio.sleep(0.05)          # da prvi stigne uzeti lock
        drugi = await c.post("/api/listen")
        assert drugi.status_code == 409
        assert (await prvi).status_code == 200


@pytest.mark.parametrize("nevaljano", [0.5, 61.0])
def test_odbija_besmisleno_trajanje_u_konfiguraciji(tmp_path, nevaljano):
    """Zastita da netko ne upise 0.1 s ili pola sata u config.local.yaml."""
    from pydantic import ValidationError

    from rpictl.config import load_config

    with pytest.raises(ValidationError):
        load_config(_config(tmp_path, listen={"clip_seconds": nevaljano}))
