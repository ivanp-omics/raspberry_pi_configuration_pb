"""HTTP i WebSocket sucelje.

Ovdje nema poslovne logike - samo prevodenje zahtjeva u pozive servisa.
Ako se ovdje pojavi neko pravilo o temperaturi, na krivom je mjestu.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path
from typing import Any, Literal

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .bus import Bus
from .clock import build_clock
from .config import Config, load_config
from .hal.factory import build_hal
from .models import FanMode, Priority
from .services.announcer import AnnouncerService
from .services.climate import ClimateService
from .services.inventory import InventoryService
from .services.music import MusicService
from .services.telemetry import TelemetryService

log = logging.getLogger(__name__)
WEB_DIR = Path(__file__).parent / "web"


# --------------------------------------------------------------------------
# Tijela zahtjeva
# --------------------------------------------------------------------------

class FanRequest(BaseModel):
    mode: FanMode


class AnnounceRequest(BaseModel):
    text: str | None = None
    file: str | None = None
    priority: Priority = Priority.NORMAL


class MusicRequest(BaseModel):
    action: Literal["play", "stop"]
    track: str | None = None


class FaultRequest(BaseModel):
    freeze: bool | None = None
    error: bool | None = None
    garbage: bool | None = None
    delay_s: float | None = Field(default=None, ge=0.0, le=30.0)


# --------------------------------------------------------------------------
# Sastavljanje aplikacije
# --------------------------------------------------------------------------

class Runtime:
    """Drzi sve zive komponente i njihove taskove."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.clock = build_clock(cfg.simulate, cfg.sim_speed)
        self.bus = Bus()
        self.hal = build_hal(cfg, self.clock)

        self.climate = ClimateService(
            cfg.climate, self.clock, self.bus, self.hal.sensor, self.hal.fan
        )
        self.announcer = AnnouncerService(self.clock, self.bus, self.hal.audio)
        self.music = MusicService(self.clock, self.bus, self.hal.music)
        self.inventory = InventoryService(
            cfg.network, self.clock, self.bus, self.hal.scanner
        )
        self.telemetry = TelemetryService(cfg.telemetry, self.clock, self.bus)
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        await self.telemetry.start()
        for svc in (self.telemetry, self.climate, self.announcer, self.music, self.inventory):
            self._tasks.append(asyncio.create_task(svc.run(), name=svc.name))
        log.info("pokrenuto %d servisa", len(self._tasks))

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await t
        await self.telemetry.close()
        await self.hal.close()
        log.info("zaustavljeno")

    def status(self) -> dict[str, Any]:
        return {
            "simulate": self.cfg.simulate,
            "sim_speed": self.cfg.sim_speed if self.cfg.simulate else 1.0,
            "now": self.clock.now(),
            "climate": self.climate.snapshot(),
            "announcer": self.announcer.snapshot(),
            "music": self.music.snapshot(),
            "network": {
                k: v for k, v in self.inventory.snapshot().items() if k != "hosts"
            },
            "telemetry": self.telemetry.snapshot(),
        }


def create_app(config_path: str = "config.yaml") -> FastAPI:
    cfg = load_config(config_path)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        rt = Runtime(cfg)
        app.state.rt = rt
        await rt.start()
        try:
            yield
        finally:
            await rt.stop()

    app = FastAPI(title="rpictl", version="0.1.0", lifespan=lifespan)

    def rt() -> Runtime:
        return app.state.rt

    async def require_token(x_api_key: str | None = Header(default=None)) -> None:
        """Provjera dijeljenog tokena - vidi ServerConfig.api_token.

        None (default) znaci da API nema svoju bravu, jer je dosad jedina
        brava bila Tailscale mreza sama. Kad je token postavljen (npr. za
        Tailscale Funnel/WordPress bridge), postaje jedina zastita jer API
        tad postaje dohvatljiv i izvan tailneta.
        """
        token = rt().cfg.server.api_token
        if token and x_api_key != token:
            raise HTTPException(status_code=401, detail="neispravan ili nedostajuci token")

    # -- citanje ------------------------------------------------------------

    @app.get("/api/status", dependencies=[Depends(require_token)])
    async def status() -> dict:
        return rt().status()

    @app.get("/api/health")
    async def health() -> JSONResponse:
        s = rt().climate.snapshot()
        ok = bool(s["healthy"])
        return JSONResponse(
            {"ok": ok, "reason": s["reason"]}, status_code=200 if ok else 503
        )

    @app.get("/api/history", dependencies=[Depends(require_token)])
    async def history(hours: float = 24.0, limit: int = 500) -> list[dict]:
        return await rt().telemetry.history(hours=hours, limit=limit)

    @app.get("/api/network", dependencies=[Depends(require_token)])
    async def network() -> dict:
        return rt().inventory.snapshot()

    # -- upravljanje --------------------------------------------------------

    @app.post("/api/fan", dependencies=[Depends(require_token)])
    async def set_fan(req: FanRequest) -> dict:
        await rt().climate.set_mode(req.mode)
        return rt().climate.snapshot()

    @app.post("/api/announce", dependencies=[Depends(require_token)])
    async def announce(req: AnnounceRequest) -> dict:
        try:
            ann = rt().announcer.enqueue(
                text=req.text, path=req.file, priority=req.priority
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"id": ann.id, "pending": rt().announcer.pending}

    @app.post("/api/music", dependencies=[Depends(require_token)])
    async def music(req: MusicRequest) -> dict:
        if req.action == "play":
            await rt().music.play(req.track)
        else:
            await rt().music.stop()
        return rt().music.snapshot()

    # -- ubrizgavanje kvarova (samo u simulaciji) ---------------------------

    @app.get("/api/sim/fault", dependencies=[Depends(require_token)])
    async def get_fault() -> dict:
        sensor = rt().hal.sensor
        if not hasattr(sensor, "fault"):
            raise HTTPException(status_code=404, detail="dostupno samo u simulaciji")
        return {**sensor.fault.to_dict(), "model_room_c": round(sensor.room_c, 2)}

    @app.post("/api/sim/fault", dependencies=[Depends(require_token)])
    async def set_fault(req: FaultRequest) -> dict:
        sensor = rt().hal.sensor
        if not hasattr(sensor, "fault"):
            raise HTTPException(status_code=404, detail="dostupno samo u simulaciji")
        for field, value in req.model_dump(exclude_none=True).items():
            setattr(sensor.fault, field, value)
        log.warning("ubrizgan kvar: %s", sensor.fault.to_dict())
        return sensor.fault.to_dict()

    # -- dogadaji uzivo -----------------------------------------------------

    @app.websocket("/ws")
    async def ws(sock: WebSocket) -> None:
        await sock.accept()
        q = rt().bus.subscribe()
        try:
            await sock.send_json({"type": "status", "data": rt().status()})
            while True:
                msg = await q.get()
                await sock.send_json(msg)
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        except Exception:  # noqa: BLE001
            log.debug("websocket prekinut", exc_info=True)
        finally:
            rt().bus.unsubscribe(q)

    # -- sucelje ------------------------------------------------------------

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
    return app
