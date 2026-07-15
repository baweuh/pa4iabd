"""Extended instrumentation (poc2.4, 2026-07-15): capture classification,
density, effective population size. All observational — see src/diagnostics.py
and DiagnosticsConfig. Migrated (with a calibration fix) from
tools/apple_capture_probe.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pytest

from src.apple import Apple
from src.config import AgentConfig, DiagnosticsConfig, SensorConfig
from src.diagnostics import (
    ADJACENT,
    DIRECTED,
    UNDIRECTED,
    capture_lookback_ticks,
    classify_capture,
    effective_population_size,
    global_density,
    local_agent_density,
    local_apple_density,
)


@dataclass
class _Point:
    """Minimal (x, y) stand-in — local_*_density only reads these two fields."""

    x: float
    y: float


def _sensors(max_distance: float = 283.0) -> SensorConfig:
    return SensorConfig(num_rays=16, max_distance=max_distance, fov=360)


def _agent_cfg(max_speed: float = 2.122) -> AgentConfig:
    return AgentConfig(
        radius=11.31,
        max_speed=max_speed,
        initial_energy=1.0,
        max_energy=2.0,
        energy_drain_per_tick=0.0004,
        max_age=5000,
        reproduction_threshold=1.1,
        reproduction_cost=0.35,
        end_of_life_ticks=500,
        max_turn_rate=0.2,
        move_cost=0.0,
        apples_per_offspring=1.5,
    )


# --------------------------------------------------------------------------- #
# capture_lookback_ticks
# --------------------------------------------------------------------------- #
def test_capture_lookback_derived_from_speed() -> None:
    # ceil(283 / 2.122) = 134
    assert capture_lookback_ticks(_sensors(), _agent_cfg()) == 134


def test_capture_lookback_halves_when_speed_doubles() -> None:
    lo = capture_lookback_ticks(_sensors(), _agent_cfg(max_speed=2.0))
    hi = capture_lookback_ticks(_sensors(), _agent_cfg(max_speed=4.0))
    assert hi == pytest.approx(lo / 2, abs=1)


def test_capture_lookback_at_least_one() -> None:
    assert (
        capture_lookback_ticks(_sensors(max_distance=1.0), _agent_cfg(max_speed=1000.0))
        == 1
    )


# --------------------------------------------------------------------------- #
# classify_capture
# --------------------------------------------------------------------------- #
def test_classify_adjacent_when_already_close() -> None:
    cfg = DiagnosticsConfig()
    # Reference point 1 unit from the apple, reach 10 -> well within close_mult*reach.
    category = classify_capture(0.0, 0.0, 1.0, 0.0, 0.0, reach=10.0, cfg=cfg)
    assert category == ADJACENT


def test_classify_directed_when_ahead_and_closed_gap() -> None:
    cfg = DiagnosticsConfig()
    # Apple straight ahead (heading 0 = +x), agent starts far, reach small ->
    # ratio = (100-1)/100 = 0.99 >= 0.6, bearing 0 <= 90.
    category = classify_capture(100.0, 0.0, 0.0, 0.0, 0.0, reach=1.0, cfg=cfg)
    assert category == DIRECTED


def test_classify_undirected_when_apple_behind() -> None:
    cfg = DiagnosticsConfig()
    # Apple is BEHIND the agent's heading (heading 0, apple at -x): ahead=False.
    category = classify_capture(-100.0, 0.0, 0.0, 0.0, 0.0, reach=1.0, cfg=cfg)
    assert category == UNDIRECTED


def test_classify_undirected_when_ahead_but_gap_not_closed() -> None:
    cfg = DiagnosticsConfig()
    # Ahead (bearing 0), dist0=100, reach=50: not adjacent (100 > 1.5*50=75),
    # but ratio=(100-50)/100=0.5 < capture_directed_ratio (0.6) -> undirected.
    category = classify_capture(100.0, 0.0, 0.0, 0.0, 0.0, reach=50.0, cfg=cfg)
    assert category == UNDIRECTED


# --------------------------------------------------------------------------- #
# local density
# --------------------------------------------------------------------------- #
def test_local_agent_density_excludes_self() -> None:
    me = _Point(0.0, 0.0)
    others = [me, _Point(10.0, 0.0), _Point(200.0, 0.0)]
    assert local_agent_density(me, others, radius=50.0) == 1  # only the 10.0 one


def test_local_apple_density_excludes_self() -> None:
    apple = Apple(0.0, 0.0)
    apples = [apple, Apple(5.0, 5.0), Apple(1000.0, 0.0)]
    assert local_apple_density(apple, apples, radius=50.0) == 1


def test_local_density_zero_when_alone() -> None:
    me = _Point(0.0, 0.0)
    assert local_agent_density(me, [me], radius=50.0) == 0


def test_global_density_is_count_over_area() -> None:
    assert global_density(100, 10.0, 10.0) == pytest.approx(1.0)
    assert global_density(0, 10.0, 10.0) == 0.0


# --------------------------------------------------------------------------- #
# effective_population_size (N_e)
# --------------------------------------------------------------------------- #
def test_ne_equals_n_when_nobody_reproduced() -> None:
    assert effective_population_size([0, 0, 0, 0]) == 4.0


def test_ne_equals_n_when_reproduction_is_perfectly_even() -> None:
    # Zero variance -> Ne == N (selection not concentrated on anyone).
    assert effective_population_size([2, 2, 2, 2]) == pytest.approx(4.0)


def test_ne_drops_below_n_when_reproduction_is_concentrated() -> None:
    # One individual hogs all the offspring: high variance -> Ne << N.
    n = effective_population_size([10, 0, 0, 0])
    assert 0.0 < n < 4.0


def test_ne_zero_population_returns_zero() -> None:
    assert effective_population_size([]) == 0.0


def test_ne_matches_crow_kimura_formula_by_hand() -> None:
    counts = [3, 1, 0, 0]
    n = len(counts)
    mean_k = sum(counts) / n
    var_k = sum((k - mean_k) ** 2 for k in counts) / n
    expected = n / (1.0 + var_k / mean_k)
    assert effective_population_size(counts) == pytest.approx(expected)
