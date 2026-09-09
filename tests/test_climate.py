"""Testovi termostata.

Ovdje se placa najveci dio duga. ThermostatPolicy je cista i sinkrona, pa
osam sati rada odsimuliramo u milisekundama - vrijeme je samo broj koji
predajemo.
"""

from __future__ import annotations

import math
import random

import pytest

from rpictl.config import ClimateConfig
from rpictl.models import FanMode, Reading
from rpictl.services.climate import ThermostatPolicy


def cfg(**kw) -> ClimateConfig:
    base = dict(
        poll_interval_s=30.0, temp_on_c=26.0, temp_off_c=24.0,
        min_on_s=180.0, min_off_s=180.0, stale_after_s=300.0,
        valid_min_c=-20.0, valid_max_c=80.0,
    )
    base.update(kw)
    return ClimateConfig(**base)


def r(ts: float, t: float) -> Reading:
    return Reading(ts=ts, temperature_c=t)


# --- osnovna histereza -----------------------------------------------------

def test_pocinje_ukljuceno_dok_nema_ocitanja():
    p = ThermostatPolicy(cfg())
    d = p.decide(0.0, None, FanMode.AUTO)
    assert d.fan_on is True
    assert d.healthy is False


def test_gasi_ispod_donjeg_praga():
    p = ThermostatPolicy(cfg())
    d = p.decide(0.0, r(0.0, 23.0), FanMode.AUTO)
    assert d.fan_on is False
    assert d.healthy is True


def test_ne_pali_u_mrtvoj_zoni():
    p = ThermostatPolicy(cfg())
    p.decide(0.0, r(0.0, 23.0), FanMode.AUTO)          # ugasi
    d = p.decide(1000.0, r(1000.0, 25.5), FanMode.AUTO)  # izmedu pragova
    assert d.fan_on is False


def test_pali_iznad_gornjeg_praga():
    p = ThermostatPolicy(cfg())
    p.decide(0.0, r(0.0, 23.0), FanMode.AUTO)
    d = p.decide(1000.0, r(1000.0, 26.4), FanMode.AUTO)
    assert d.fan_on is True


# --- minimalna vremena -----------------------------------------------------

def test_min_on_time_drzi_ventilator_upaljen():
    p = ThermostatPolicy(cfg())
    p.decide(0.0, r(0.0, 23.0), FanMode.AUTO)     # off, t=0
    p.decide(500.0, r(500.0, 27.0), FanMode.AUTO)  # on,  t=500
    # 60 s kasnije naglo zahladi - svejedno mora nastaviti raditi
    d = p.decide(560.0, r(560.0, 20.0), FanMode.AUTO)
    assert d.fan_on is True
    assert "minimalno vrijeme rada" in d.reason
    # nakon isteka min_on_s smije se ugasiti
    d = p.decide(690.0, r(690.0, 20.0), FanMode.AUTO)
    assert d.fan_on is False


def test_min_off_time_drzi_ventilator_ugasen():
    p = ThermostatPolicy(cfg())
    p.decide(0.0, r(0.0, 23.0), FanMode.AUTO)
    d = p.decide(60.0, r(60.0, 30.0), FanMode.AUTO)
    assert d.fan_on is False
    assert "minimalno vrijeme mirovanja" in d.reason


# --- fail-safe -------------------------------------------------------------

def test_zastarjelo_ocitanje_pali_ventilator():
    p = ThermostatPolicy(cfg())
    p.decide(0.0, r(0.0, 20.0), FanMode.AUTO)
    stale = r(0.0, 20.0)
    d = p.decide(400.0, stale, FanMode.AUTO)   # 400 s > stale_after_s
    assert d.fan_on is True
    assert d.healthy is False


def test_besmisleno_ocitanje_pali_ventilator():
    p = ThermostatPolicy(cfg())
    p.decide(0.0, r(0.0, 20.0), FanMode.AUTO)
    d = p.decide(300.0, r(300.0, -40.0), FanMode.AUTO)
    assert d.fan_on is True
    assert d.healthy is False


def test_oporavak_nakon_kvara():
    p = ThermostatPolicy(cfg())
    p.decide(0.0, None, FanMode.AUTO)
    d = p.decide(1000.0, r(1000.0, 22.0), FanMode.AUTO)
    assert d.fan_on is False
    assert d.healthy is True


# --- rucni nacini ----------------------------------------------------------

def test_rucni_nacini_gaze_temperaturu():
    p = ThermostatPolicy(cfg())
    assert p.decide(0.0, r(0.0, 40.0), FanMode.OFF).fan_on is False
    assert p.decide(10.0, r(10.0, 5.0), FanMode.ON).fan_on is True


def test_konfiguracija_bez_histereze_se_odbija():
    with pytest.raises(ValueError):
        cfg(temp_on_c=25.0, temp_off_c=25.0)


# --- ono zbog cega histereza uopce postoji ---------------------------------

def _run_noise(policy: ThermostatPolicy, seed: int = 1) -> int:
    """8 sati temperature koja sjedi tocno na pragu, sa sumom senzora."""
    rng = random.Random(seed)
    t = 0.0
    for _ in range(960):            # 8 sati po 30 s
        policy.decide(t, r(t, 25.0 + rng.gauss(0.0, 0.4)), FanMode.AUTO)
        t += 30.0
    return policy.cycles


def test_histereza_drasticno_smanjuje_ciklanje():
    """Ovo je jedini razlog zasto histereza postoji. Bez nje relej i
    ventilator odlaze u par mjeseci."""
    bez = _run_noise(ThermostatPolicy(
        cfg(temp_on_c=25.05, temp_off_c=24.95, min_on_s=0.0, min_off_s=0.0)))
    sa = _run_noise(ThermostatPolicy(cfg()))
    assert bez > 100, f"kontrolni slucaj nije ciklao ({bez})"
    assert sa < bez / 10, f"histereza ne pomaze dovoljno: {sa} vs {bez}"


def test_minimalna_vremena_dodatno_priguse_ciklanje():
    sa_min = _run_noise(ThermostatPolicy(cfg()))
    bez_min = _run_noise(ThermostatPolicy(cfg(min_on_s=0.0, min_off_s=0.0)))
    assert sa_min <= bez_min


def test_dnevni_ciklus_daje_razuman_broj_paljenja():
    """Sinusoidalni dan koji prelazi oba praga: ocekujemo par paljenja,
    ne desetke."""
    p = ThermostatPolicy(cfg())
    t = 0.0
    for i in range(2880):           # 24 h po 30 s
        hour = (t / 3600.0) % 24.0
        temp = 25.0 + 3.0 * math.sin(2 * math.pi * (hour - 9.0) / 24.0)
        p.decide(t, r(t, temp), FanMode.AUTO)
        t += 30.0
    assert 1 <= p.cycles <= 6, f"neocekivan broj ciklusa: {p.cycles}"
