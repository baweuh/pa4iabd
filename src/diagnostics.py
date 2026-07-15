"""Observational instrumentation: capture classification, density, N_e.

Every function here is read-only with respect to the simulation: pure
functions over positions/counts, never fed back into agent decisions,
reproduction or mutation (CSV-only diagnostics). Capture classification
migrates the heuristic from ``tools/apple_capture_probe.py`` (2026-07-09 ad
hoc probe) into a permanent runtime metric — see that module's docstring for
the original heuristic and ``docs/RESULTS-density.md`` for the calibration
bug fixed here (the probe's fixed ``lookback=30`` ticks did not scale with
``agent.max_speed``; the window is now derived, see
:func:`capture_lookback_ticks`).
"""

from __future__ import annotations

import math
import statistics as st
from typing import TYPE_CHECKING

from src.config import AgentConfig, DiagnosticsConfig, SensorConfig
from src.novelty import probe_apple_on_ray

if TYPE_CHECKING:
    from src.agent import Agent
    from src.apple import Apple
    from src.network import NeuralNetwork

ADJACENT = "adjacent"
DIRECTED = "directed"
UNDIRECTED = "undirected"


def steer_score(net: "NeuralNetwork", sensors: SensorConfig) -> float:
    """Pearson r between 'apple on the left' and 'turns left'.

    1.0 = perfect forager, 0.0 = ignores apples, negative = anti-forager.
    Deterministic from the (frozen) network — a lone synthetic apple is
    placed on each egocentric ray in turn and the turn response measured, no
    world/population state involved. Migrated from ``tools/steer_probe.py``
    (offline champion-vs-random-baseline analysis) into a permanent runtime
    metric (``Simulation._log_row``'s ``mean_steer_score``/``forager_pct``).
    """
    num_rays = sensors.num_rays
    xs: list[float] = []
    ys: list[float] = []
    for k in range(1, num_rays):
        if k == num_rays // 2:
            continue  # directly behind: ambiguous
        ang = k * (2 * math.pi / num_rays)
        raw = net.activate(probe_apple_on_ray(k, sensors))
        xs.append(math.sin(ang))
        ys.append(math.tanh(raw[1]))
    mx, my = st.mean(xs), st.mean(ys)
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    dy = math.sqrt(sum((b - my) ** 2 for b in ys))
    return num / (dx * dy) if dx * dy > 1e-12 else 0.0


def capture_lookback_ticks(sensors: SensorConfig, agent: AgentConfig) -> int:
    """Ticks needed to cross the whole sensing range once, at max speed (>= 1).

    Derived from config, not hardcoded (invariant n°1): scales automatically
    with ``agent.max_speed``, fixing the probe's old fixed ``lookback=30``
    (silently miscalibrated once max_speed was halved, poc2.4 density lever).
    """
    return max(1, math.ceil(sensors.max_distance / agent.max_speed))


def classify_capture(
    apple_x: float,
    apple_y: float,
    ref_x: float,
    ref_y: float,
    ref_heading: float,
    reach: float,
    cfg: DiagnosticsConfig,
) -> str:
    """Classify one capture from the agent's reference position/heading.

    ``ref_*`` is the agent's position/heading at (or just after) the apple's
    own ``spawn_tick`` — approaching a spot before the apple existed there
    isn't "directed" toward it. Three categories:

    - ``adjacent``: the agent was already within ``capture_close_mult × reach``
      of the apple back then — no real travel needed, a "free" catch.
    - ``directed``: the apple was ahead (egocentric bearing within
      ``capture_ahead_degrees``) and the agent closed at least
      ``capture_directed_ratio`` of the initial gap — genuine steering.
    - ``undirected``: neither — consistent with a random-walk collision.
    """
    dist0 = math.hypot(apple_x - ref_x, apple_y - ref_y)
    if dist0 <= reach * cfg.capture_close_mult:
        return ADJACENT
    bearing = math.atan2(apple_y - ref_y, apple_x - ref_x) - ref_heading
    bearing = (bearing + math.pi) % (2.0 * math.pi) - math.pi
    ahead = abs(math.degrees(bearing)) <= cfg.capture_ahead_degrees
    ratio = max(0.0, (dist0 - reach) / dist0)
    return DIRECTED if (ahead and ratio >= cfg.capture_directed_ratio) else UNDIRECTED


def local_agent_density(
    agent: "Agent", population: list["Agent"], radius: float
) -> int:
    """Count of OTHER agents within ``radius`` of ``agent`` (excludes itself)."""
    r2 = radius * radius
    return sum(
        1
        for other in population
        if other is not agent
        and (other.x - agent.x) ** 2 + (other.y - agent.y) ** 2 <= r2
    )


def local_apple_density(apple: "Apple", apples: list["Apple"], radius: float) -> int:
    """Count of OTHER apples within ``radius`` of ``apple`` (excludes itself)."""
    r2 = radius * radius
    return sum(
        1
        for other in apples
        if other is not apple
        and (other.x - apple.x) ** 2 + (other.y - apple.y) ** 2 <= r2
    )


def global_density(count: int, world_width: float, world_height: float) -> float:
    """Count per unit area — a single map-wide number (agents or apples)."""
    return count / (world_width * world_height)


def effective_population_size(offspring_counts: list[int]) -> float:
    """Crow & Kimura N_e ≈ N / (1 + Var(k) / mean(k)) — quantifies drift vs
    selection: N_e << N means reproductive success is concentrated on a few
    lineages (drift-dominated); N_e ≈ N means success is broadly shared
    (selection acting on a wide base without being swamped by variance).

    ``offspring_counts`` must have one entry per individual in the reference
    population (0 for anyone who didn't reproduce) — N is ``len(offspring_counts)``.

    APPROXIMATION for this project's overlapping-generation model (agents of
    many ages reproducing continuously, no discrete generations to align on):
    the caller uses a rolling tick window and the CURRENTLY ALIVE population
    as N, so parents that died mid-window are simply absent from both N and
    the offspring counts — a known undercount, acceptable for a rolling
    diagnostic (not a textbook per-generation N_e).
    """
    n = len(offspring_counts)
    if n == 0:
        return 0.0
    mean_k = sum(offspring_counts) / n
    if mean_k <= 0.0:
        return float(n)
    var_k = st.pvariance(offspring_counts)
    return n / (1.0 + var_k / mean_k)
