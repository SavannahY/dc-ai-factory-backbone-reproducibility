"""Unit tests for transparent screening-model primitives.

These tests intentionally focus on invariant behaviour and reference-case
regressions. They are not a substitute for project-specific EMT, harmonic, or
hardware validation, but they make accidental numerical drift visible in CI.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ai_dc_backbone.dynamics import lpf, spectral_energy
from ai_dc_backbone.efficiency import losses_eff
from ai_dc_backbone.harmonics import resonance_factor


def test_reference_efficiency_losses_match_archived_case() -> None:
    """Guard the central 1 GW, 20 km loss calculation."""

    losses = losses_eff()

    assert losses["Traditional AC"] == pytest.approx(39.12461631186497, rel=1e-12)
    assert losses["Local SST"] == pytest.approx(26.49903090586567, rel=1e-12)
    assert losses["Subtransmission DC backbone"] == pytest.approx(
        25.704284346690656, rel=1e-12
    )


def test_efficiency_model_has_expected_sensitivity_direction() -> None:
    """The model should expose, not hide, the high-efficiency SST counter-case."""

    reference = losses_eff()
    high_efficiency_sst = losses_eff(sst_eff=0.990)

    assert reference["Subtransmission DC backbone"] < reference["Traditional AC"]
    assert reference["Subtransmission DC backbone"] < reference["Local SST"]
    assert high_efficiency_sst["Local SST"] < reference["Subtransmission DC backbone"]


def test_first_order_filter_step_response_is_bounded_and_monotone() -> None:
    x = np.concatenate([np.zeros(10), np.ones(90)])
    y = lpf(x, tau=2.0, dt=0.1)

    assert y[0] == pytest.approx(0.0)
    assert np.all(y >= -1e-15)
    assert np.all(y <= 1.0 + 1e-15)
    assert np.all(np.diff(y[10:]) >= -1e-15)
    assert y[-1] > 0.98


def test_spectral_energy_rejects_constant_signal() -> None:
    x = np.ones(4096) * 123.4
    assert spectral_energy(x, dt=0.01) == pytest.approx(0.0, abs=1e-12)


def test_spectral_energy_detects_in_band_signal() -> None:
    dt = 0.001
    t = np.arange(0, 10, dt)
    in_band = 3.0 * np.sin(2 * math.pi * 1.0 * t)
    above_band = 7.0 * np.sin(2 * math.pi * 30.0 * t)

    assert spectral_energy(in_band, dt=dt) == pytest.approx(3.0, rel=2e-3)
    assert spectral_energy(above_band, dt=dt) == pytest.approx(0.0, abs=1e-10)


def test_harmonic_resonance_factor_is_finite_and_peaked() -> None:
    orders = np.linspace(2, 35, 200)
    factors = np.array([resonance_factor(float(h)) for h in orders])

    assert np.all(np.isfinite(factors))
    assert np.all(factors >= 1.0)
    assert resonance_factor(11) > resonance_factor(5)
    assert resonance_factor(23) > resonance_factor(17)
