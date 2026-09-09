"""Pravi BME680 preko I2C.

Biblioteka je blokirajuca i cita se sporo (gas senzor grije plocicu), pa
sve ide u thread da ne zaustavlja asyncio petlju.
"""

from __future__ import annotations

import asyncio
import logging

from ..clock import Clock
from ..models import Reading, SensorError

log = logging.getLogger(__name__)


class Bme680Sensor:
    def __init__(self, clock: Clock, address: int = 0x76) -> None:
        self._clock = clock
        try:
            import bme680  # type: ignore
        except ImportError as exc:  # pragma: no cover - samo na Pi-ju
            raise SensorError(
                "nedostaje paket 'bme680'. Na Pi-ju: pip install bme680 smbus2"
            ) from exc

        self._mod = bme680
        try:
            self._dev = bme680.BME680(address)
        except (IOError, OSError) as exc:
            raise SensorError(
                f"BME680 se ne javlja na adresi {address:#04x}. "
                "Provjeri i2cdetect -y 1 i je li I2C ukljucen u raspi-config."
            ) from exc

        self._dev.set_humidity_oversample(bme680.OS_2X)
        self._dev.set_pressure_oversample(bme680.OS_4X)
        self._dev.set_temperature_oversample(bme680.OS_8X)
        self._dev.set_filter(bme680.FILTER_SIZE_3)
        self._dev.set_gas_status(bme680.ENABLE_GAS_MEAS)
        self._dev.set_gas_heater_temperature(320)
        self._dev.set_gas_heater_duration(150)
        self._dev.select_gas_heater_profile(0)

    def _read_blocking(self) -> Reading:
        if not self._dev.get_sensor_data():
            raise SensorError("BME680 nema svjezih podataka")
        d = self._dev.data
        return Reading(
            ts=self._clock.now(),
            temperature_c=round(d.temperature, 2),
            humidity_pct=round(d.humidity, 1),
            pressure_hpa=round(d.pressure, 1),
            gas_ohms=round(d.gas_resistance, 0) if d.heat_stable else None,
        )

    async def read(self) -> Reading:
        try:
            return await asyncio.to_thread(self._read_blocking)
        except SensorError:
            raise
        except (IOError, OSError) as exc:
            raise SensorError(f"I2C greska: {exc}") from exc

    async def close(self) -> None:
        log.debug("BME680 zatvoren")
