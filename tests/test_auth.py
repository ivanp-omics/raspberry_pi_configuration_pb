"""Testovi dijeljenog tokena na /api rutama - vidi ServerConfig.api_token.

Kad token nije postavljen (default), API se ponasa identicno kao prije -
Tailscale mreza je jedina brava. Kad je postavljen (npr. za Tailscale Funnel
+ WordPress bridge), postaje jedina zastita jer API tad postaje dohvatljiv
i izvan tailneta.
"""

from __future__ import annotations

from types import SimpleNamespace

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


class _StubRuntime:
    """Samo ono sto /ws pogleda prije nego odbije vezu."""

    def __init__(self, token: str | None) -> None:
        self.cfg = SimpleNamespace(server=SimpleNamespace(api_token=token))


async def _ws_close_code(app, query: str = "") -> int | None:
    """Kojim kodom aplikacija zatvori WebSocket vezu, ako je uopce zatvori.

    Zove ASGI aplikaciju izravno, bez TestClienta i bez vlastite petlje
    dogadaja. Oboje je namjerno: TestClientov websocket transport zna tvrdo
    srusiti proces pri gasenju (Python 3.14 + Windows), a asyncio.run()
    unutar njega dodaje drugu petlju na isti proces i pogorsa stvar.
    """
    sent: list[dict] = []

    async def receive() -> dict:
        return {"type": "websocket.connect"}

    async def send(message: dict) -> None:
        sent.append(message)

    scope = {
        "type": "websocket",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "scheme": "ws",
        "path": "/ws",
        "raw_path": b"/ws",
        "query_string": query.encode(),
        "root_path": "",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 8000),
        "subprotocols": [],
    }
    await app(scope, receive, send)
    assert all(m["type"] != "websocket.accept" for m in sent), "veza je prihvacena"
    return next((m.get("code") for m in sent if m["type"] == "websocket.close"), None)


async def test_websocket_bez_tokena_pada(tmp_path):
    """Bez ovoga je /ws jedina ruta koja curi zivo stanje bilo kome."""
    app = create_app(_write_config(tmp_path, token="tajna"))
    app.state.rt = _StubRuntime("tajna")
    assert await _ws_close_code(app) == 1008


async def test_websocket_s_krivim_tokenom_pada(tmp_path):
    app = create_app(_write_config(tmp_path, token="tajna"))
    app.state.rt = _StubRuntime("tajna")
    assert await _ws_close_code(app, "token=kriva") == 1008


def test_websocket_s_tokenom_prolazi(tmp_path):
    app = create_app(_write_config(tmp_path, token="tajna"))
    with TestClient(app) as c, c.websocket_connect("/ws?token=tajna") as sock:
        assert sock.receive_json()["type"] == "status"


def test_websocket_bez_postavljenog_tokena_radi_kao_prije(tmp_path):
    app = create_app(_write_config(tmp_path, token=None))
    with TestClient(app) as c, c.websocket_connect("/ws") as sock:
        assert sock.receive_json()["type"] == "status"
