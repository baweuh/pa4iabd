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
            "apples_per_offspring": 0.0,  # energy-based reproduction
        },
        population={"initial_size": 5, "max_size": 6},
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
            "apples_per_offspring": 0.0,  # energy-based reproduction
        },
        population={"initial_size": 2, "max_size": 3},
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
            "apples_per_offspring": 0.0,  # energy-based reproduction
        },
        population={"initial_size": 1, "max_size": 10},
    )
    sim = Simulation(cfg, random.Random(7))
    sim.env.apples.clear()
    sim.population[0].energy = 2.5  # can afford ≥3 reproductions at cost 0.3
    sim.tick()
    assert sim.total_reproductions >= 2  # at least two children this tick


def test_max_children_per_tick_caps_energy_path(tmp_path):
    # Truncation softening (research-roadmap chantier n°2): even with ample
    # energy and free slots, one agent may not produce more than the cap.
    cfg = build_config(
        tmp_path,
        agent={
            "initial_energy": 3.0,
            "max_energy": 3.0,
            "reproduction_threshold": 0.5,
            "reproduction_cost": 0.3,
            "apples_per_offspring": 0.0,  # energy-based reproduction
            "max_children_per_tick": 1,
        },
        population={"initial_size": 1, "max_size": 10},
    )
    sim = Simulation(cfg, random.Random(7))
    sim.env.apples.clear()
    sim.population[0].energy = 3.0  # uncapped would afford ~8 children here
    sim.tick()
    assert sim.total_reproductions == 1


def test_max_children_per_tick_spills_to_next_agent(tmp_path):
    # Without the cap the top-priority agent alone would drain every open
    # slot (test_multi_offspring_high_energy); with cap=1 the runner-up gets
    # a slot too instead of being starved out by greedy truncation.
    cfg = build_config(
        tmp_path,
        agent={
            "initial_energy": 3.0,
            "max_energy": 3.0,
            "reproduction_threshold": 0.5,
            "reproduction_cost": 0.3,
            "apples_per_offspring": 0.0,  # energy-based reproduction
            "max_children_per_tick": 1,
        },
        population={"initial_size": 2, "max_size": 10},
    )
    sim = Simulation(cfg, random.Random(8))
    sim.env.apples.clear()
    top, second = sim.population
    top.energy, top.generation = cfg.agent.max_energy, 10
    second.energy, second.generation = 2.0, 20  # also easily above threshold

    sim.tick()

    assert sim.total_reproductions == 2  # one slot each, no agent capped out
    generations = {a.generation for a in sim.population}
    assert 11 in generations  # top parent's child
    assert 21 in generations  # runner-up also got a slot


def test_max_children_per_tick_zero_is_legacy_unbounded(tmp_path):
    # 0 (default) must reproduce test_multi_offspring_high_energy's uncapped
    # behaviour byte-for-byte: same config, no max_children_per_tick override.
    cfg = build_config(
        tmp_path,
        agent={
            "initial_energy": 2.0,
            "max_energy": 3.0,
            "reproduction_threshold": 0.5,
            "reproduction_cost": 0.3,
            "apples_per_offspring": 0.0,
        },
        population={"initial_size": 1, "max_size": 10},
    )
    sim = Simulation(cfg, random.Random(7))
    sim.env.apples.clear()
    sim.population[0].energy = 2.5
    sim.tick()
    assert sim.total_reproductions >= 2


def test_max_children_per_tick_caps_foraging_legacy_path(tmp_path):
    cfg = build_config(
        tmp_path,
        agent={
            "apples_per_offspring": 2.0,
            "initial_energy": 2.0,
            "max_energy": 3.0,
            "reproduction_cost": 0.1,
            "max_children_per_tick": 1,
        },
        population={"initial_size": 1, "max_size": 10},
    )
    sim = Simulation(cfg, random.Random(6))
    sim.env.apples.clear()
    agent = sim.population[0]
    agent.energy = cfg.agent.max_energy
    sim._repro_credit[agent] = 10.0  # uncapped would give floor(10/2) = 5 children

    sim.tick()

    assert sim.total_reproductions == 1
    assert sim._repro_credit[agent] == pytest.approx(
        8.0
    )  # only one child's credit spent


# ------------------------------------------------------------------ #
# Round-robin reproduction (truncation softening, take 2)
# ------------------------------------------------------------------ #


def test_round_robin_splits_evenly_between_competing_agents(tmp_path):
    # Breadth-first softening: with two competing agents, round-robin gives
    # each ONE child per pass instead of letting the top-priority agent claim
    # every slot before the runner-up is even looked at (contrast with
    # test_reproduction_prioritises_highest_energy_at_cap's legacy behaviour).
    cfg = build_config(
        tmp_path,
        agent={
            "initial_energy": 3.0,
            "max_energy": 3.0,
            "reproduction_threshold": 0.5,
            "reproduction_cost": 0.3,
            "apples_per_offspring": 0.0,  # energy-based reproduction
            "reproduction_round_robin": True,
        },
        population={"initial_size": 2, "max_size": 6},
    )
    sim = Simulation(cfg, random.Random(8))
    sim.env.apples.clear()
    top, second = sim.population
    top.energy, top.generation = cfg.agent.max_energy, 10  # higher priority
    second.energy, second.generation = 2.0, 20

    sim.tick()  # 4 free slots (6 - 2 survivors)

    assert sim.total_reproductions == 4
    gens = [a.generation for a in sim.population]
    assert gens.count(11) == 2  # top parent: 2, not all 4
    assert gens.count(21) == 2  # runner-up: 2 too, not shut out


def test_round_robin_no_ceiling_without_competition(tmp_path):
    # Unlike a flat max_children_per_tick cap, round-robin never artificially
    # limits a SOLE eligible agent — with nobody to alternate with, it still
    # claims every open slot, just spread across successive passes.
    cfg = build_config(
        tmp_path,
        agent={
            "initial_energy": 2.0,
            "max_energy": 3.0,
            "reproduction_threshold": 0.5,
            "reproduction_cost": 0.3,
            "apples_per_offspring": 0.0,
            "reproduction_round_robin": True,
        },
        population={"initial_size": 1, "max_size": 10},
    )
    sim = Simulation(cfg, random.Random(7))
    sim.env.apples.clear()
    sim.population[0].energy = 2.5
    sim.tick()
    assert sim.total_reproductions >= 2  # matches the uncapped legacy result


def test_round_robin_splits_foraging_credit_under_slot_scarcity(tmp_path):
    # Same breadth-first split on the foraging-credit path, this time under
    # slot scarcity so legacy-vs-round-robin actually diverge: legacy would
    # give the richer forager 3 children and the poorer one only 1 (its
    # credit priced out once slots run low); round-robin gives 2 and 2.
    cfg = build_config(
        tmp_path,
        agent={
            "apples_per_offspring": 2.0,
            "initial_energy": 3.0,
            "max_energy": 3.0,
            "reproduction_cost": 0.1,
            "reproduction_round_robin": True,
        },
        population={"initial_size": 2, "max_size": 6},
    )
    sim = Simulation(cfg, random.Random(6))
    sim.env.apples.clear()
    rich, poor = sim.population
    rich.energy = poor.energy = cfg.agent.max_energy
    rich.generation, poor.generation = 10, 20
    sim._repro_credit[rich] = 6.0  # 3 children worth, uncontested
    sim._repro_credit[poor] = 4.0  # 2 children worth, uncontested

    sim.tick()  # 4 free slots (6 - 2 survivors), less than 3+2=5 needed

    assert sim.total_reproductions == 4
    gens = [a.generation for a in sim.population]
    assert gens.count(11) == 2  # NOT 3: round-robin yields the richer forager
    assert gens.count(21) == 2  # NOT 1: the poorer forager isn't shut out
    assert sim._repro_credit[rich] == pytest.approx(2.0)
    assert sim._repro_credit[poor] == pytest.approx(0.0)


def test_round_robin_off_by_default_is_legacy(tmp_path):
    # False (default): behaviour must match the pre-existing greedy test
    # (test_reproduction_prioritises_highest_energy_at_cap) byte-for-byte.
    cfg = build_config(
        tmp_path,
        agent={
            "initial_energy": 1.0,
            "max_energy": 2.0,
            "reproduction_threshold": 0.5,
            "reproduction_cost": 0.3,
            "apples_per_offspring": 0.0,
        },
        population={"initial_size": 2, "max_size": 3},
    )
    sim = Simulation(cfg, random.Random(6))
    sim.env.apples.clear()
    high, low = sim.population
    high.energy, high.generation = cfg.agent.max_energy, 10
    low.energy, low.generation = cfg.agent.reproduction_threshold + 0.05, 3

    sim.tick()

    assert sim.total_reproductions == 1
    generations = {a.generation for a in sim.population}
    assert 11 in generations
    assert 4 not in generations


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
        population={"initial_size": 2, "max_size": 10},
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


def _foraging_sim(tmp_path, min_ticks, per_child=2.0):
    """Single-agent foraging-reproduction sim with the minimal-criterion gate."""
    cfg = build_config(
        tmp_path,
        agent={
            "apples_per_offspring": per_child,
            "initial_energy": 2.0,
            "max_energy": 3.0,
            "reproduction_cost": 0.1,
            "reproduction_min_ticks": min_ticks,
        },
        population={"initial_size": 1, "max_size": 10},
    )
    sim = Simulation(cfg, random.Random(6))
    sim.env.apples.clear()  # no eating; credit is set by hand
    sim.population[0].energy = cfg.agent.max_energy
    return sim


def test_min_ticks_zero_is_legacy_greedy(tmp_path):
    """min_ticks=0 (default): a well-fed forager still empties its credit in one tick."""
    sim = _foraging_sim(tmp_path, min_ticks=0)
    agent = sim.population[0]
    sim._repro_credit[agent] = 6.0  # 3 children worth at per_child=2
    sim.tick()
    assert sim.total_reproductions == 3  # greedy: all credit spent at once
    assert sim._repro_credit[agent] == pytest.approx(0.0)


def test_min_ticks_gate_blocks_until_sustained(tmp_path):
    """With min_ticks>0 an agent must HOLD credit for that many ticks before a birth."""
    sim = _foraging_sim(tmp_path, min_ticks=3)
    agent = sim.population[0]
    sim._repro_credit[agent] = 4.0  # enough credit, but streak starts at 0

    sim.tick()  # streak 1
    sim.tick()  # streak 2
    assert sim.total_reproductions == 0  # not sustained long enough yet

    sim.tick()  # streak 3 -> qualifies
    assert sim.total_reproductions == 1


def test_min_ticks_one_child_per_tick_then_refractory(tmp_path):
    """A qualifying agent produces exactly ONE child and its streak resets."""
    sim = _foraging_sim(tmp_path, min_ticks=2)
    agent = sim.population[0]
    sim._repro_credit[agent] = 100.0  # plenty — legacy path would dump ~50 children
    sim._credit_streak[agent] = 1  # one tick short of the gate

    sim.tick()  # streak -> 2, qualifies: exactly one birth, streak resets
    assert sim.total_reproductions == 1
    assert sim._repro_credit[agent] == pytest.approx(98.0)  # spent one per_child
    assert sim._credit_streak[agent] == 0  # refractory period begins


def test_credit_streak_resets_when_credit_drops(tmp_path):
    """The streak only counts consecutive ticks at/above threshold; a dip resets it."""
    sim = _foraging_sim(tmp_path, min_ticks=5)
    agent = sim.population[0]
    sim._repro_credit[agent] = 4.0
    sim.tick()  # streak 1
    sim.tick()  # streak 2
    assert sim._credit_streak[agent] == 2

    sim._repro_credit[agent] = 0.5  # below per_child=2 now
    sim.tick()
    assert sim._credit_streak[agent] == 0  # reset, must re-accumulate and re-sustain


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
        population={"initial_size": 1, "max_size": 10},
    )
    sim = Simulation(cfg, random.Random(7))
    sim.env.apples.clear()
    sim.population[0].energy = 2.5  # high energy → energy-driven multi-offspring
    sim._repro_credit[sim.population[0]] = 0.0  # no apple credit at all
    sim.tick()
    assert sim.total_reproductions >= 2  # legacy energy path still fires


# ------------------------------------------------------------------ #
# Fitness sharing (speciation.fitness_sharing — species-relative priority)
# ------------------------------------------------------------------ #
def _split_into_dominant_pair_and_novel(cfg, sim):
    """3 living agents: dominant_a/dominant_b share one (size-2) species,
    novel diverges enough to form its own (size-1) species."""
    dominant_a, dominant_b, novel = sim.population
    dominant_b.genome = dominant_a.genome.clone()
    rng = random.Random(3)
    for _ in range(5):  # > compatibility_threshold worth of excess genes
        novel.genome.add_node(cfg.genome, rng)
    return dominant_a, dominant_b, novel


def test_fitness_sharing_off_by_default(tmp_path):
    assert build_config(tmp_path).speciation.fitness_sharing is False


def test_fitness_sharing_off_keeps_raw_priority(tmp_path):
    cfg = build_config(
        tmp_path,
        agent={
            "initial_energy": 1.0,
            "max_energy": 2.0,
            "reproduction_threshold": 0.5,
            "reproduction_cost": 0.05,
            "apples_per_offspring": 0.0,
        },
        population={"initial_size": 3, "max_size": 4},
        novelty={"enabled": False},  # isolate raw priority (novelty is on by default)
    )
    sim = Simulation(cfg, random.Random(9))
    sim.env.apples.clear()
    dominant_a, dominant_b, novel = _split_into_dominant_pair_and_novel(cfg, sim)
    dominant_a.energy, dominant_a.generation = 1.0, 10  # raw fitness winner
    dominant_b.energy, dominant_b.generation = 0.1, 20  # ineligible, pads the species
    novel.energy, novel.generation = 0.6, 30  # raw fitness loser

    sim.tick()  # one free slot (4 - 3 survivors)

    generations = {a.generation for a in sim.population}
    assert 11 in generations  # dominant_a wins on raw energy alone
    assert 31 not in generations


def test_fitness_sharing_on_lets_small_species_outrank_larger_one(tmp_path):
    cfg = build_config(
        tmp_path,
        agent={
            "initial_energy": 1.0,
            "max_energy": 2.0,
            "reproduction_threshold": 0.5,
            "reproduction_cost": 0.05,
            "apples_per_offspring": 0.0,
        },
        population={"initial_size": 3, "max_size": 4},
        speciation={"fitness_sharing": True},
        novelty={
            "enabled": False
        },  # isolate fitness sharing (novelty is on by default)
    )
    sim = Simulation(cfg, random.Random(9))
    sim.env.apples.clear()
    dominant_a, dominant_b, novel = _split_into_dominant_pair_and_novel(cfg, sim)
    dominant_a.energy, dominant_a.generation = 1.0, 10  # shared: 1.0 / 2 = 0.5
    dominant_b.energy, dominant_b.generation = 0.1, 20  # ineligible, pads the species
    novel.energy, novel.generation = 0.6, 30  # shared: 0.6 / 1 = 0.6 → wins

    sim.tick()  # one free slot (4 - 3 survivors)

    generations = {a.generation for a in sim.population}
    assert 31 in generations  # novel's shared fitness beats dominant_a's diluted one
    assert 11 not in generations
