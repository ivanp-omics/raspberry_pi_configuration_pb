"""Testovi dijeljenog tokena na /api rutama - vidi ServerConfig.api_token.

Kad token nije postavljen (default), API se ponasa identicno kao prije -
Tailscale mreza je jedina brava. Kad je postavljen (npr. za Tailscale Funnel
+ WordPress bridge), postaje jedina zastita jer API tad postaje dohvatljiv
i izvan tailneta.
"""

from __future__ import annotations

import yaml
from fastapi.testclient import TestClient

from rpictl.app import create_app


def _write_config(tmp_path, token: str | None) -> str:
    cfg: dict = {
        "simulate": True,
        "sim_speed": 60.0,
        "server": {"host": "127.0.0.1", "port": 8000},
        "telemetry": {"db_path": str(tmp_path / "test.sqlite")},
    }
    if token:
        cfg["server"]["api_token"] = token
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return str(path)


def test_bez_tokena_sve_prolazi_kao_prije(tmp_path):
    app = create_app(_write_config(tmp_path, token=None))
    with TestClient(app) as c:
        assert c.get("/api/status").status_code == 200
        assert c.post("/api/fan", json={"mode": "auto"}).status_code == 200


def test_s_tokenom_zahtjev_bez_headera_pada(tmp_path):
    app = create_app(_write_config(tmp_path, token="tajna"))
    with TestClient(app) as c:
        assert c.get("/api/status").status_code == 401
        assert c.post("/api/fan", json={"mode": "auto"}).status_code == 401


def test_s_tokenom_krivi_header_pada(tmp_path):
    app = create_app(_write_config(tmp_path, token="tajna"))
    with TestClient(app) as c:
        r = c.get("/api/status", headers={"X-Api-Key": "kriva"})
        assert r.status_code == 401


def test_s_tokenom_ispravan_header_prolazi(tmp_path):
    app = create_app(_write_config(tmp_path, token="tajna"))
    with TestClient(app) as c:
        r = c.get("/api/status", headers={"X-Api-Key": "tajna"})
        assert r.status_code == 200
        r = c.post(
            "/api/fan", json={"mode": "auto"}, headers={"X-Api-Key": "tajna"}
        )
        assert r.status_code == 200


def test_health_ne_treba_token(tmp_path):
    app = create_app(_write_config(tmp_path, token="tajna"))
    with TestClient(app) as c:
        assert c.get("/api/health").status_code in (200, 503)
