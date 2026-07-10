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
    """Omitting the section -> disabled; present -> parsed as written."""
    import copy

    import yaml

    raw = yaml.safe_load(open("config/default.yaml", encoding="utf-8"))
    raw = copy.deepcopy(raw)
    raw.pop("novelty", None)  # a pre-novelty config has no such section
    assert SimConfig.from_dict(raw).novelty == NoveltyConfig()  # -> disabled

    lever = SimConfig.from_yaml("config/lever_novelty.yaml").novelty
    assert lever.enabled and lever.weight > 0.0


# --------------------------------------------------------------------------- #
# Additive priority (the core behavioural claim)
# --------------------------------------------------------------------------- #
def test_priority_off_returns_raw_unchanged() -> None:
    """Both modifiers off -> the exact raw callable, zero-cost legacy path."""
    from dataclasses import replace

    cfg = SimConfig.from_yaml("config/default.yaml")
    cfg = replace(cfg, novelty=NoveltyConfig())  # novelty off (default has it on)
    sim = Simulation(cfg, Random(42))
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


def test_priority_call_populates_novelty_scores() -> None:
    """A priority call refreshes the per-agent cached novelty scores."""
    sim = _sim("config/lever_novelty.yaml")
    assert all(a.novelty_score == 0.0 for a in sim.population)  # before
    sim._priority_fn(sim.population, lambda a: 1.0)
    assert any(a.novelty_score > 0.0 for a in sim.population)  # after refresh


def test_recompute_interval_gates_rescoring() -> None:
    """With interval>1, novelty is rescored once then reused until interval passes."""
    from dataclasses import replace

    sim = _sim("config/lever_novelty.yaml")
    sim._config = replace(
        sim._config, novelty=replace(sim._config.novelty, recompute_interval=50)
    )
    raw = lambda a: 1.0  # noqa: E731

    sim._priority_fn(sim.population, raw)  # first call: refreshes
    first_tick = sim._last_novelty_tick
    assert first_tick == sim.tick_count
    scores_before = [a.novelty_score for a in sim.population]

    sim.tick_count += 10  # advance, but < interval
    sim._priority_fn(sim.population, raw)  # must NOT re-refresh
    assert sim._last_novelty_tick == first_tick
    assert [a.novelty_score for a in sim.population] == scores_before
