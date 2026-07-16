"""Behavioural novelty: descriptor, population scoring, and additive priority.

Guards the poc2.4 research lever #3 (novelty search, Lehman & Stanley 2011) wired
as an ADDITIVE reproduction bonus. Checks the descriptor is deterministic, the
novelty score rewards behavioural outliers, the config section is optional, and
the priority modifier only ever *adds* (never penalises) — the property that
distinguishes it from the falsified reducer mechanisms.
"""

from __future__ import annotations

from collections import deque
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


def test_novelty_archive_widens_neighbourhood() -> None:
    """A tight cluster looks less novel once an archive of outliers exists.

    ``neighbors=4`` exceeds the cluster's 3 other members, so without an
    archive ``k`` caps at 3 (all in-cluster). With the archive, the pool grows
    and ``k`` reaches 4 — forcing in one distant archive point, which raises
    the mean distance.
    """
    cluster = np.array([[0.0, 0.0], [0.01, 0.0], [0.0, 0.01], [0.01, 0.01]])
    without_archive = population_novelty(cluster, neighbors=4)

    archive = np.array([[5.0, 5.0], [5.0, -5.0], [-5.0, 5.0], [-5.0, -5.0]])
    with_archive = population_novelty(cluster, neighbors=4, archive=archive)
    assert np.all(with_archive > without_archive)


def test_novelty_archive_never_scored_itself() -> None:
    """Archive shape matches the scored population, not descriptors+archive."""
    descriptors = np.zeros((3, 2))
    archive = np.array([[9.0, 9.0]])
    novelty = population_novelty(descriptors, neighbors=5, archive=archive)
    assert novelty.shape == (3,)


def test_novelty_archive_lone_agent_not_zero() -> None:
    """A single survivor has 0 novelty vs an empty pool but not vs an archive."""
    descriptor = np.zeros((1, 2))
    archive = np.array([[3.0, 3.0]])
    assert population_novelty(descriptor, neighbors=5, archive=archive)[0] > 0.0


# --------------------------------------------------------------------------- #
# max_pool_size (poc3: bounds the O(pop²) cost at large population)
# --------------------------------------------------------------------------- #
def test_max_pool_size_zero_is_unchanged_from_before_the_param_existed() -> None:
    rng = np.random.default_rng(0)
    descriptors = rng.normal(size=(30, 4))
    default = population_novelty(descriptors, neighbors=5)
    explicit_unlimited = population_novelty(descriptors, neighbors=5, max_pool_size=0)
    assert np.array_equal(default, explicit_unlimited)


def test_max_pool_size_at_or_above_pool_is_exact() -> None:
    """No subsampling kicks in once max_pool_size >= the pool itself."""
    rng = np.random.default_rng(1)
    descriptors = rng.normal(size=(20, 3))
    exact = population_novelty(descriptors, neighbors=5)
    capped_wide = population_novelty(
        descriptors, neighbors=5, max_pool_size=20, rng=Random(0)
    )
    assert np.array_equal(exact, capped_wide)


def test_max_pool_size_caps_cost_and_stays_deterministic() -> None:
    """Same seed -> identical subsample -> identical scores (determinism)."""
    rng = np.random.default_rng(2)
    descriptors = rng.normal(size=(50, 4))
    a = population_novelty(descriptors, neighbors=5, max_pool_size=10, rng=Random(7))
    b = population_novelty(descriptors, neighbors=5, max_pool_size=10, rng=Random(7))
    assert np.array_equal(a, b)
    assert a.shape == (50,)
    assert np.all(np.isfinite(a))  # no stray inf leaking into the mean


def test_max_pool_size_excludes_self_even_when_sampled() -> None:
    """An agent identical to itself must never count itself as a neighbour,
    even when the random subsample happens to include its own index."""
    descriptors = np.zeros((5, 2))  # every agent identical -> any nonzero
    # score would mean self wasn't excluded.
    for seed in range(20):  # try enough seeds that self gets sampled at least once
        novelty = population_novelty(
            descriptors, neighbors=2, max_pool_size=3, rng=Random(seed)
        )
        assert np.all(novelty == 0.0)


def test_max_pool_size_with_archive() -> None:
    """Subsampling composes with the archive (pool = descriptors ∪ archive)."""
    rng = np.random.default_rng(3)
    descriptors = rng.normal(size=(15, 3))
    archive = rng.normal(size=(15, 3)) + 10.0  # visibly distant cluster
    novelty = population_novelty(
        descriptors, neighbors=5, archive=archive, max_pool_size=8, rng=Random(1)
    )
    assert novelty.shape == (15,)
    assert np.all(np.isfinite(novelty))


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

    archive_lever = SimConfig.from_yaml("config/lever_novelty_archive.yaml").novelty
    assert archive_lever.archive_enabled and not lever.archive_enabled


def test_max_pool_size_defaults_zero_and_rejects_negative() -> None:
    import copy

    import pytest
    import yaml

    from src.config import ConfigError

    raw = copy.deepcopy(yaml.safe_load(open("config/default.yaml", encoding="utf-8")))
    assert SimConfig.from_dict(raw).novelty.max_pool_size == 0

    raw["novelty"] = {"max_pool_size": -1}
    with pytest.raises(ConfigError, match="max_pool_size must be >= 0"):
        SimConfig.from_dict(raw)


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


def test_archive_off_never_populates() -> None:
    """archive_enabled=False (default) -> archive stays empty however many refreshes."""
    sim = _sim("config/lever_novelty.yaml")  # archive off
    for _ in range(5):
        sim._priority_fn(sim.population, lambda a: 1.0)  # noqa: B023
        sim.tick_count += sim._config.novelty.recompute_interval
    assert len(sim._novelty_archive) == 0


def test_archive_on_accumulates_and_is_capped() -> None:
    """archive_enabled=True with prob=1.0 -> every scored agent archived, FIFO-capped."""
    from dataclasses import replace

    sim = _sim("config/lever_novelty_archive.yaml")
    sim._config = replace(
        sim._config,
        novelty=replace(sim._config.novelty, archive_prob=1.0, archive_max_size=10),
    )
    sim._novelty_archive = deque(sim._novelty_archive, maxlen=10)
    sim._priority_fn(sim.population, lambda a: 1.0)
    assert len(sim._novelty_archive) == 10  # capped, not len(population)


def test_archive_feeds_back_into_scoring() -> None:
    """A pre-seeded archive changes novelty scores vs the same run without one.

    ``neighbors`` is pushed past the population size so ``k`` always covers
    every other point in the pool — with the archive that pool has one extra
    member, so the mean-distance denominator (and near-certainly the sum)
    differs from the archive-less run of the same seeded config.
    """
    from dataclasses import replace

    def make_sim() -> Simulation:
        sim = _sim("config/lever_novelty_archive.yaml")
        big_k = len(sim.population) + 50
        sim._config = replace(
            sim._config, novelty=replace(sim._config.novelty, neighbors=big_k)
        )
        return sim

    sim_plain = make_sim()
    sim_plain._priority_fn(sim_plain.population, lambda a: 1.0)
    plain_scores = [a.novelty_score for a in sim_plain.population]

    sim_archived = make_sim()
    outlier = -np.ones(sim_archived._config.sensors.num_rays) * 10.0
    sim_archived._novelty_archive.append(outlier)
    sim_archived._priority_fn(sim_archived.population, lambda a: 1.0)
    archived_scores = [a.novelty_score for a in sim_archived.population]

    assert archived_scores != plain_scores


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
