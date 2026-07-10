"""Behavioural novelty: descriptor, population scoring, and additive priority.

Guards the poc2.4 research lever #3 (novelty search, Lehman & Stanley 2011) wired
as an ADDITIVE reproduction bonus. Checks the descriptor is deterministic, the
novelty score rewards behavioural outliers, the config section is optional, and
the priority modifier only ever *adds* (never penalises) — the property that
distinguishes it from the falsified reducer mechanisms.
"""

from __future__ import annotations

from random import Random

import numpy as np

from src.config import NoveltyConfig, SimConfig
from src.novelty import behavior_descriptor, population_novelty
from src.simulation import Simulation


def _sim(config_path: str, seed: int = 42) -> Simulation:
    return Simulation(SimConfig.from_yaml(config_path), Random(seed))


# --------------------------------------------------------------------------- #
# Descriptor
# --------------------------------------------------------------------------- #
def test_descriptor_deterministic_and_length() -> None:
    """Same network -> identical descriptor of length num_rays."""
    sim = _sim("config/default.yaml")
    agent = sim.population[0]
    d1 = behavior_descriptor(agent.network, sim._config.sensors)
    d2 = behavior_descriptor(agent.network, sim._config.sensors)
    assert d1 == d2
    assert len(d1) == sim._config.sensors.num_rays


def test_agent_caches_descriptor() -> None:
    """Agent.behavior_descriptor is memoised (computed once, same object back)."""
    agent = _sim("config/default.yaml").population[0]
    first = agent.behavior_descriptor
    assert agent.behavior_descriptor is first  # cached, not recomputed


def test_descriptor_valid_for_rich_layout() -> None:
    """Works for the 67-input layout too (probe mirrors sense() toggles)."""
    sim = _sim("config/apple_repro_bigpop67.yaml")
    d = behavior_descriptor(sim.population[0].network, sim._config.sensors)
    assert len(d) == sim._config.sensors.num_rays


# --------------------------------------------------------------------------- #
# Population novelty
# --------------------------------------------------------------------------- #
def test_novelty_outlier_scores_higher() -> None:
    """A behavioural outlier is more novel than members of a tight cluster."""
    cluster = np.array([[0.0, 0.0], [0.01, 0.0], [0.0, 0.01], [0.01, 0.01]])
    outlier = np.array([[5.0, 5.0]])
    descriptors = np.vstack([cluster, outlier])
    novelty = population_novelty(descriptors, neighbors=2)
    assert novelty[-1] == novelty.max()
    assert novelty[-1] > novelty[0]


def test_novelty_edge_cases() -> None:
    """0 and 1 agents -> all-zero novelty (no crash, no self-distance)."""
    assert population_novelty(np.zeros((0, 3)), 5).shape == (0,)
    assert list(population_novelty(np.zeros((1, 3)), 5)) == [0.0]


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
def test_novelty_section_optional() -> None:
    """Absent section -> disabled; the lever config -> enabled."""
    assert SimConfig.from_yaml("config/default.yaml").novelty == NoveltyConfig()
    lever = SimConfig.from_yaml("config/lever_novelty.yaml").novelty
    assert lever.enabled and lever.weight > 0.0


# --------------------------------------------------------------------------- #
# Additive priority (the core behavioural claim)
# --------------------------------------------------------------------------- #
def test_priority_off_returns_raw_unchanged() -> None:
    """Both modifiers off -> the exact raw callable, zero-cost legacy path."""
    sim = _sim("config/default.yaml")
    raw = lambda a: a.energy  # noqa: E731
    assert sim._priority_fn(sim.population, raw) is raw


def test_priority_novelty_adds_bonus_favouring_novel_agent() -> None:
    """With equal raw fitness, priority is highest for the most novel agent."""
    sim = _sim("config/lever_novelty.yaml")
    survivors = sim.population
    priority = sim._priority_fn(survivors, lambda a: 1.0)  # constant base

    # Independently: which survivor is the behavioural outlier?
    descriptors = np.array([a.behavior_descriptor for a in survivors])
    novelty = population_novelty(descriptors, sim._config.novelty.neighbors)
    most_novel = survivors[int(np.argmax(novelty))]

    scores = {a: priority(a) for a in survivors}
    assert scores[most_novel] == max(scores.values())
    # Additive: every agent's priority is >= its base (never penalised).
    assert all(v >= 1.0 for v in scores.values())
