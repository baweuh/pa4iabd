"""Tests for Simulation (Phase 6): tick order, population, CSV, best genome."""

# pylint: disable=missing-function-docstring,protected-access,redefined-outer-name

from __future__ import annotations

import copy
import csv
import random
from pathlib import Path

import pytest
import yaml

from src.apple import Apple
from src.config import SimConfig
from src.genome import Genome
from src.simulation import CSV_HEADER, Simulation

DEFAULT_YAML = Path(__file__).resolve().parents[1] / "config" / "default.yaml"


def build_config(tmp_path: Path, **overrides: dict) -> SimConfig:
    """Default config with section overrides and logging redirected to tmp_path."""
    raw = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))
    raw = copy.deepcopy(raw)
    raw["logging"]["csv_path"] = str(tmp_path / "metrics.csv")
    raw["logging"]["best_genome_path"] = str(tmp_path / "best_genome.json")
    for section, values in overrides.items():
        raw[section].update(values)
    return SimConfig.from_dict(raw)


@pytest.fixture(name="cfg")
def cfg_fixture(tmp_path):
    return build_config(tmp_path)


# ------------------------------------------------------------------ #
# Initialisation
# ------------------------------------------------------------------ #


def test_initial_population_size(cfg):
    sim = Simulation(cfg, random.Random(1))
    assert sim.population_size == cfg.population.initial_size


def test_initial_agents_in_safe_zone(cfg):
    sim = Simulation(cfg, random.Random(1))
    for agent in sim.population:
        assert sim.env.in_safe_zone(agent.x, agent.y)


def test_determinism(cfg):
    sim_a = Simulation(cfg, random.Random(7))
    sim_b = Simulation(cfg, random.Random(7))
    for a, b in zip(sim_a.population, sim_b.population):
        assert (a.x, a.y) == (b.x, b.y)


# ------------------------------------------------------------------ #
# Tick order / counters
# ------------------------------------------------------------------ #


def test_tick_advances_counter_and_ages(cfg):
    sim = Simulation(cfg, random.Random(2))
    started = list(sim.population)  # newborns/floor refills (age 0) may join this tick
    sim.tick()
    assert sim.tick_count == 1
    assert all(a.age == 1 for a in started)


def test_tick_applies_metabolism(cfg):
    # Far from any apple it cannot reach, energy must drop by at least the base drain.
    sim = Simulation(cfg, random.Random(3))
    sim.env.apples.clear()
    before = [a.energy for a in sim.population]
    sim.tick()
    for energy_before, agent in zip(before, sim.population):
        assert (
            agent.energy
            == pytest.approx(energy_before - cfg.agent.energy_drain_per_tick)
            or agent.energy < energy_before
        )


# ------------------------------------------------------------------ #
# Eating + deferred respawn through the pipeline
# ------------------------------------------------------------------ #


def _single_agent_on_apple(sim: Simulation) -> None:
    """Reduce the world to one agent sitting on a single apple."""
    agent = sim.population[0]
    cx, cy = sim._config.world.width / 2, sim._config.world.height / 2
    agent.x, agent.y = cx, cy
    sim.population = [agent]
    sim._apples_eaten = {agent: 0}
    sim.env.apples[:] = [Apple(cx, cy)]
    sim.env._pending.clear()


def test_eating_removes_food_then_it_respawns(tmp_path):
    cfg = build_config(tmp_path, apple={"respawn_delay": 5})
    sim = Simulation(cfg, random.Random(4))
    _single_agent_on_apple(sim)

    sim.tick()
    assert sim.food_available == 0  # eaten this tick, now pending

    for _ in range(cfg.apple.respawn_delay + 1):
        sim.tick()
    assert sim.food_available == 1  # returned after the delay


def test_record_and_best_genome_saved(tmp_path):
    cfg = build_config(tmp_path, apple={"respawn_delay": 5})
    sim = Simulation(cfg, random.Random(5))
    _single_agent_on_apple(sim)

    sim.tick()
    assert sim.record_apples >= 1
    run_dir = Path(cfg.logging.csv_path).parent / sim.run_id
    saved = list((run_dir / "best_agents").glob("agent_*.json"))
    assert len(saved) >= 1
    restored = Genome.from_json(saved[0].read_text(encoding="utf-8"))
    assert isinstance(restored, Genome)


def test_latest_best_genome_written_at_configured_name(tmp_path):
    cfg = build_config(tmp_path, apple={"respawn_delay": 5})
    sim = Simulation(cfg, random.Random(5))
    _single_agent_on_apple(sim)

    sim.tick()
    run_dir = Path(cfg.logging.csv_path).parent / sim.run_id
    latest = run_dir / Path(cfg.logging.best_genome_path).name
    assert latest.exists()
    archived = sorted((run_dir / "best_agents").glob("agent_*.json"))
    assert latest.read_text(encoding="utf-8") == archived[-1].read_text(
        encoding="utf-8"
    )


# ------------------------------------------------------------------ #
# Reproduction + population cap
# ------------------------------------------------------------------ #


def test_reproduction_increments_and_respects_cap(tmp_path):
    cfg = build_config(
        tmp_path,
        agent={
            "initial_energy": 1.0,
            "reproduction_threshold": 0.5,
            "reproduction_cost": 0.3,
        },
        population={"initial_size": 5, "min_size": 1, "max_size": 6},
    )
    sim = Simulation(cfg, random.Random(6))
    sim.tick()
    assert sim.total_reproductions >= 1
    assert sim.population_size <= cfg.population.max_size


# ------------------------------------------------------------------ #
# Extinction
# ------------------------------------------------------------------ #


def test_extinction_stops_run(tmp_path):
    cfg = build_config(
        tmp_path,
        agent={
            "initial_energy": 0.5,
            "max_energy": 1.0,
            "energy_drain_per_tick": 5.0,
            "reproduction_threshold": 0.9,
            "reproduction_cost": 0.5,
        },
        apple={"energy": 0.001, "respawn_delay": 5},
    )
    sim = Simulation(cfg, random.Random(8))
    sim.run()
    assert sim.is_extinct
    assert sim.population_size == 0


# ------------------------------------------------------------------ #
# CSV logging
# ------------------------------------------------------------------ #


def test_csv_header_and_rows(tmp_path):
    cfg = build_config(
        tmp_path,
        simulation={"ticks_per_second": 60, "max_ticks": 3, "seed": 42},
        logging={
            "csv_path": str(tmp_path / "metrics.csv"),
            "log_interval_ticks": 1,
            "best_genome_path": str(tmp_path / "best_genome.json"),
        },
    )
    sim = Simulation(cfg, random.Random(9))
    sim.run()

    run_csv = Path(cfg.logging.csv_path).parent / sim.run_id / "metrics.csv"
    rows = list(csv.reader(run_csv.open(encoding="utf-8")))
    assert tuple(rows[0]) == CSV_HEADER
    assert len(rows) == 1 + 3  # header + one row per tick (interval 1, 3 ticks)
    # Columns are parsable: tick is an int, avg_lifespan a float.
    first = rows[1]
    assert int(first[0]) == 1
    assert float(first[4]) >= 0.0


def test_csv_has_evolutionary_columns(tmp_path):
    cfg = build_config(
        tmp_path,
        simulation={"ticks_per_second": 60, "max_ticks": 2, "seed": 42},
        logging={
            "csv_path": str(tmp_path / "metrics.csv"),
            "log_interval_ticks": 1,
            "best_genome_path": str(tmp_path / "best_genome.json"),
        },
    )
    sim = Simulation(cfg, random.Random(11))
    sim.run()

    run_csv = Path(cfg.logging.csv_path).parent / sim.run_id / "metrics.csv"
    rows = list(csv.reader(run_csv.open(encoding="utf-8")))
    header = rows[0]
    assert tuple(header) == CSV_HEADER
    for col in (
        "max_generation",
        "mean_generation",
        "species_count",
        "mean_genetic_distance",
        "mean_forage_rate",
        "max_forage_rate",
    ):
        assert col in header
    row = dict(zip(header, rows[1]))
    assert int(row["max_generation"]) >= 0
    assert int(row["species_count"]) >= 1  # a live population has at least one species
    assert float(row["mean_genetic_distance"]) >= 0.0
    assert float(row["mean_forage_rate"]) >= 0.0


def test_reproduction_prioritises_highest_energy_at_cap(tmp_path):
    cfg = build_config(
        tmp_path,
        agent={
            "initial_energy": 1.0,
            "max_energy": 2.0,
            "reproduction_threshold": 0.5,
            "reproduction_cost": 0.3,
        },
        population={"initial_size": 2, "min_size": 1, "max_size": 3},
    )
    sim = Simulation(cfg, random.Random(6))
    sim.env.apples.clear()  # no eating: keep the energy ordering we set
    high, low = sim.population
    high.energy, high.generation = cfg.agent.max_energy, 10
    low.energy, low.generation = cfg.agent.reproduction_threshold + 0.05, 3

    sim.tick()  # one free slot (3 - 2 survivors), both eligible

    assert sim.total_reproductions == 1
    generations = {a.generation for a in sim.population}
    assert 11 in generations  # high-energy parent's child
    assert 4 not in generations  # low-energy parent did NOT win the slot


def test_elite_reinjected_on_record(tmp_path):
    cfg = build_config(tmp_path, apple={"respawn_delay": 5})
    sim = Simulation(cfg, random.Random(5))
    _single_agent_on_apple(sim)
    assert len(sim.population) == 1

    sim.tick()  # agent eats apple → new record → elite clone injected
    assert sim.record_apples >= 1
    assert len(sim.population) >= 2  # original agent + elite (+ possible child)


def test_multi_offspring_high_energy(tmp_path):
    cfg = build_config(
        tmp_path,
        agent={
            "initial_energy": 2.0,
            "max_energy": 3.0,
            "reproduction_threshold": 0.5,
            "reproduction_cost": 0.3,
        },
        population={"initial_size": 1, "min_size": 1, "max_size": 10},
    )
    sim = Simulation(cfg, random.Random(7))
    sim.env.apples.clear()
    sim.population[0].energy = 2.5  # can afford ≥3 reproductions at cost 0.3
    sim.tick()
    assert sim.total_reproductions >= 2  # at least two children this tick


def test_csv_interval_respected(tmp_path):
    cfg = build_config(
        tmp_path,
        simulation={"ticks_per_second": 60, "max_ticks": 10, "seed": 42},
        logging={
            "csv_path": str(tmp_path / "metrics.csv"),
            "log_interval_ticks": 5,
            "best_genome_path": str(tmp_path / "best_genome.json"),
        },
    )
    sim = Simulation(cfg, random.Random(10))
    sim.run()

    run_csv = Path(cfg.logging.csv_path).parent / sim.run_id / "metrics.csv"
    rows = list(csv.reader(run_csv.open(encoding="utf-8")))
    # header + ticks 5 and 10 logged.
    assert len(rows) == 1 + 2
    assert int(rows[1][0]) == 5
    assert int(rows[2][0]) == 10


# ------------------------------------------------------------------ #
# Structural reproduction (fecundity from cumulative foraging)
# ------------------------------------------------------------------ #
def test_reproduction_by_foraging_scales_with_apples(tmp_path):
    # apples_per_offspring > 0 switches to foraging-coupled fecundity: offspring
    # count comes from banked apple credit, not instantaneous energy.
    cfg = build_config(
        tmp_path,
        agent={
            "apples_per_offspring": 2.0,
            "initial_energy": 2.0,
            "max_energy": 3.0,
            "reproduction_cost": 0.1,
        },
        population={"initial_size": 2, "min_size": 1, "max_size": 10},
    )
    sim = Simulation(cfg, random.Random(6))
    sim.env.apples.clear()  # no eating this tick; we set credit by hand
    rich, poor = sim.population
    rich.energy = poor.energy = cfg.agent.max_energy
    rich.generation, poor.generation = 10, 20
    sim._repro_credit[rich] = 5.0  # 5 apples of credit → floor(5/2) = 2 children
    sim._repro_credit[poor] = 1.0  # below one child's worth → 0 children

    sim.tick()

    gens = [a.generation for a in sim.population]
    assert sim.total_reproductions == 2  # only the rich forager reproduced
    assert gens.count(11) == 2  # both children came from the rich parent
    assert 21 not in gens  # poor forager (credit 1 < 2) did not reproduce
    assert sim._repro_credit[rich] == 1.0  # spent 2×2 credit, 1.0 remains


def test_apples_per_offspring_zero_keeps_legacy_energy_path(tmp_path):
    # Default 0.0 must preserve the energy-threshold reproduction (regression guard).
    cfg = build_config(
        tmp_path,
        agent={
            "apples_per_offspring": 0.0,
            "initial_energy": 2.0,
            "max_energy": 3.0,
            "reproduction_threshold": 0.5,
            "reproduction_cost": 0.3,
        },
        population={"initial_size": 1, "min_size": 1, "max_size": 10},
    )
    sim = Simulation(cfg, random.Random(7))
    sim.env.apples.clear()
    sim.population[0].energy = 2.5  # high energy → energy-driven multi-offspring
    sim._repro_credit[sim.population[0]] = 0.0  # no apple credit at all
    sim.tick()
    assert sim.total_reproductions >= 2  # legacy energy path still fires
