"""batch_sense() must be bit-identical to per-agent Agent.sense().

Guards the poc2.4 "freeze then perceive" tick: the batched perception replaces
the per-agent raycast, so it must produce EXACTLY the same NN inputs for every
agent — across every sensor layout (legacy 49 and rich 67) and the no-apple edge
case. Any drift here is a silent behavioural regression, not just a slowdown.
"""

from __future__ import annotations

from random import Random

import pytest

from src.agent import batch_sense
from src.config import SimConfig
from src.simulation import Simulation


def _evolved_sim(config_path: str, ticks: int, seed: int = 42) -> Simulation:
    cfg = SimConfig.from_yaml(config_path)
    sim = Simulation(cfg, Random(seed))
    for _ in range(ticks):
        if sim.is_extinct:
            break
        sim.tick()
    return sim


@pytest.mark.parametrize(
    "config_path",
    ["config/default.yaml", "config/apple_repro_bigpop67.yaml"],
)
def test_batch_sense_matches_per_agent(config_path: str) -> None:
    """Every row of batch_sense equals that agent's own sense(), value for value."""
    sim = _evolved_sim(config_path, ticks=400)
    assert sim.population, "population went extinct — cannot compare perception"

    reference = [agent.sense() for agent in sim.population]
    batched = batch_sense(sim.population, sim.env, sim._config)

    assert len(batched) == len(reference)
    for row_ref, row_batch in zip(reference, batched):
        assert len(row_batch) == len(row_ref) == sim._config.network.num_inputs
        # Exact equality: same NumPy ops in the same order -> identical floats.
        assert row_batch == row_ref


def test_batch_sense_no_apples() -> None:
    """With every apple pending respawn, distances clamp to max — no NaN/crash."""
    cfg = SimConfig.from_yaml("config/default.yaml")
    sim = Simulation(cfg, Random(1))
    # Remove all live apples so the circle-cast branch is skipped.
    for apple in list(sim.env.apples):
        sim.env.mark_eaten(apple)

    reference = [agent.sense() for agent in sim.population]
    batched = batch_sense(sim.population, sim.env, sim._config)
    assert batched == reference


def test_batch_sense_empty_population() -> None:
    """A dead world yields no rows (guards the zip in tick)."""
    cfg = SimConfig.from_yaml("config/default.yaml")
    sim = Simulation(cfg, Random(1))
    assert batch_sense([], sim.env, sim._config) == []
