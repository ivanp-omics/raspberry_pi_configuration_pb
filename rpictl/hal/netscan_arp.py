"""Pravi skener: ping sweep pa citanje ARP tablice.

Bez root prava i bez nmapa. Ping probudi susjede, kernel popuni ARP tablicu,
mi je procitamo. Za tocnije rezultate postavi method: nmap u konfiguraciji.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import socket
from pathlib import Path

from ..config import NetworkConfig
from ..models import Host

log = logging.getLogger(__name__)

_ARP_LINE = re.compile(
    r"^(?P<ip>\S+)\s+\S+\s+\S+\s+(?P<mac>[0-9a-f:]{17})\s+\S+\s+(?P<dev>\S+)$",
    re.IGNORECASE,
)


class ArpNetworkScanner:
    def __init__(self, cfg: NetworkConfig) -> None:
        self._cfg = cfg

    async def _ping(self, ip: str) -> None:
        try:
            proc = await asyncio.create_subprocess_exec(
                "ping", "-c", "1", "-W", "1", ip,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
        except FileNotFoundError:
            log.error("nema naredbe ping")

    async def _sweep(self) -> None:
        net = ipaddress.ip_network(self._cfg.subnet, strict=False)
        sem = asyncio.Semaphore(64)

        async def one(ip: str) -> None:
            async with sem:
                await self._ping(ip)

        await asyncio.gather(*(one(str(h)) for h in net.hosts()))

    def _read_arp(self) -> list[Host]:
        path = Path("/proc/net/arp")
        if not path.exists():
            log.warning("/proc/net/arp ne postoji - ovaj skener radi samo na Linuxu")
            return []
        hosts: list[Host] = []
        for line in path.read_text().splitlines()[1:]:
            m = _ARP_LINE.match(line.strip())
            if not m or m.group("mac") == "00:00:00:00:00:00":
                continue
            ip = m.group("ip")
            try:
                name = socket.gethostbyaddr(ip)[0]
            except OSError:
                name = None
            hosts.append(Host(mac=m.group("mac").lower(), ip=ip, hostname=name))
        return hosts

    async def _nmap(self) -> list[Host]:
        proc = await asyncio.create_subprocess_exec(
            "nmap", "-sn", "-n", self._cfg.subnet,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate()
        hosts: list[Host] = []
        ip: str | None = None
        for line in out.decode(errors="replace").splitlines():
            if line.startswith("Nmap scan report for "):
                ip = line.rsplit(" ", 1)[-1].strip("()")
            elif "MAC Address:" in line and ip:
                mac = line.split("MAC Address:")[1].split()[0].lower()
                hosts.append(Host(mac=mac, ip=ip, hostname=None))
                ip = None
        return hosts

    async def scan(self) -> list[Host]:
        if self._cfg.method == "nmap":
            try:
                return await self._nmap()
            except FileNotFoundError:
                log.error("nema nmapa, vracam se na ARP")
        await self._sweep()
        return await asyncio.to_thread(self._read_arp)

    async def close(self) -> None:
        return None
