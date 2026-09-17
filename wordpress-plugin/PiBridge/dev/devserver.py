#!/usr/bin/env python3
"""Lokalni dev server za PiBridge pregled (dev/local-preview.html).

Servira local-preview.html i ../assets/panel.{css,js}, i odgovara na
/dev-api/status, /dev-api/history, /dev-api/network, /dev-api/fan,
/dev-api/announce, /dev-api/music.

Ako dev/piconf.yaml postoji, ti pozivi idu STVARNOM Piju (server-to-server,
isti obrazac kao pibridge.php - CORS se zaobilazi jer browser uvijek zove
samo ovaj lokalni server na 127.0.0.1, nikad Pi izravno). Ako piconf.yaml
ne postoji, vraca izmisljene (mock) podatke - isto ponasanje kao prije.

Ovisi samo o Python standardnoj biblioteci - ne treba ni pip install.

Pokretanje:   python devserver.py
Zaustavljanje: Ctrl+C
"""

from __future__ import annotations

import json
import math
import random
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).parent
ASSETS = HERE.parent / "assets"
PICONF = HERE / "piconf.yaml"
PORT = 8787


def load_piconf() -> dict | None:
    """Namjerno sam parser umjesto PyYAML - piconf.yaml ima samo dva ravna
    kljuca, ne treba vanjska ovisnost samo za ovaj razvojni alat."""
    if not PICONF.exists():
        return None
    cfg: dict[str, str] = {}
    for line in PICONF.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        cfg[key.strip()] = value.strip().strip('"').strip("'")
    if not cfg.get("pi_url"):
        return None
    return cfg


# -- mock podaci (kad piconf.yaml ne postoji) -------------------------------

_mock = {
    "mode": "auto", "fan_on": True, "music": "stopped", "track": None,
    "pending": 0, "playing": None,
}


def mock_status() -> dict:
    temp = 33.5 + math.sin(time.time() / 90) * 2.5
    return {
        "simulate": False,
        "sim_speed": 1.0,
        "now": time.time(),
        "climate": {
            "mode": _mock["mode"],
            "fan_on": _mock["fan_on"],
            "reason": (
                f"{temp:.1f} C, bez promjene" if _mock["mode"] == "auto"
                else ("rucno ukljuceno" if _mock["mode"] == "on" else "rucno iskljuceno")
            ),
            "healthy": True,
            "reading": {
                "ts": time.time(), "temperature_c": temp, "humidity_pct": 47.0,
                "pressure_hpa": 1013.2, "gas_ohms": 125000,
            },
            "reading_age_s": 3, "cycles": 4, "reads": 812, "errors": 0,
            "thresholds": {"on_c": 35.0, "off_c": 32.0},
        },
        "announcer": {"pending": _mock["pending"], "playing": _mock["playing"]},
        "music": {"status": _mock["music"], "track": _mock["track"]},
        "telemetry": {},
    }


def mock_history() -> list[dict]:
    now = time.time()
    rows = []
    for i in range(144, -1, -1):
        ts = now - i * 600
        hour = (ts / 3600) % 24
        temp = 30 + 4 * math.sin(2 * math.pi * (hour - 9) / 24) + random.uniform(-0.3, 0.3)
        rows.append({"ts": ts, "temperature_c": temp, "humidity_pct": 45 + random.uniform(0, 5)})
    return rows


def mock_network() -> dict:
    return {
        "last_scan": time.time(), "scans": 120, "online": 2, "known": 3,
        "hosts": [
            {"mac": "aa:bb:cc:00:01", "ip": "192.168.8.10", "hostname": "mikser-fizika", "online": True},
            {"mac": "aa:bb:cc:00:02", "ip": "192.168.8.11", "hostname": "playlist-laptop", "online": True},
            {"mac": "aa:bb:cc:00:03", "ip": "192.168.8.30", "hostname": None, "online": False},
        ],
    }


# -- stvarni Pi (server-to-server, kao pibridge_request() u pibridge.php) --

def pi_request(cfg: dict, method: str, endpoint: str, body: dict | None = None) -> tuple[int, bytes]:
    url = cfg["pi_url"].rstrip("/") + endpoint
    data = json.dumps(body or {}).encode("utf-8") if method == "POST" else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-Api-Key", cfg.get("api_token", ""))
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except urllib.error.URLError as exc:
        msg = json.dumps({"message": f"Ne mogu se spojiti na Pi: {exc.reason}"}).encode("utf-8")
        return 502, msg


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, payload) -> None:
        body = payload if isinstance(payload, (bytes, bytearray)) else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, path: Path) -> None:
        if not path.exists():
            self.send_error(404)
            return
        ctype = {
            ".html": "text/html", ".css": "text/css", ".js": "application/javascript",
        }.get(path.suffix, "application/octet-stream")
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = self.path.split("?", 1)[0]
        cfg = load_piconf()

        if path in ("/", "/local-preview.html"):
            return self._serve_file(HERE / "local-preview.html")
        if path == "/assets/panel.css":
            return self._serve_file(ASSETS / "panel.css")
        if path == "/assets/panel.js":
            return self._serve_file(ASSETS / "panel.js")

        if path == "/dev-api/status":
            if cfg:
                status, body = pi_request(cfg, "GET", "/api/status")
                return self._json(status, body)
            return self._json(200, mock_status())
        if path == "/dev-api/history":
            if cfg:
                status, body = pi_request(cfg, "GET", "/api/history?hours=24")
                return self._json(status, body)
            return self._json(200, mock_history())
        if path == "/dev-api/network":
            if cfg:
                status, body = pi_request(cfg, "GET", "/api/network")
                return self._json(status, body)
            return self._json(200, mock_network())

        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = self.path.split("?", 1)[0]
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        req_body = json.loads(raw or b"{}")
        cfg = load_piconf()

        if path == "/dev-api/fan":
            if cfg:
                status, body = pi_request(cfg, "POST", "/api/fan", req_body)
                return self._json(status, body)
            _mock["mode"] = req_body.get("mode", _mock["mode"])
            if _mock["mode"] == "on":
                _mock["fan_on"] = True
            elif _mock["mode"] == "off":
                _mock["fan_on"] = False
            return self._json(200, mock_status()["climate"])

        if path == "/dev-api/announce":
            if cfg:
                status, body = pi_request(cfg, "POST", "/api/announce", req_body)
                return self._json(status, body)
            _mock["pending"] += 1
            _mock["playing"] = req_body.get("text")
            return self._json(200, {"id": "mock", "pending": _mock["pending"]})

        if path == "/dev-api/music":
            if cfg:
                status, body = pi_request(cfg, "POST", "/api/music", req_body)
                return self._json(status, body)
            _mock["music"] = "playing" if req_body.get("action") == "play" else "stopped"
            _mock["track"] = "playlist/ljeto-2026.mp3" if _mock["music"] == "playing" else None
            return self._json(200, mock_status()["music"])

        self.send_error(404)

    def log_message(self, fmt: str, *args) -> None:  # tisi ispis, samo greske
        pass


def main() -> None:
    cfg = load_piconf()
    print(f"PiBridge dev preview: http://127.0.0.1:{PORT}/")
    if cfg:
        print(f"STVARNI Pi (dev/piconf.yaml pronadjen): {cfg['pi_url']}")
    else:
        print("MOCK podaci (nema dev/piconf.yaml - vidi piconf.example.yaml)")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
