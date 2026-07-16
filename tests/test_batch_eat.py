"""batch_eat() must be bit-identical to calling Agent.eat() per agent in order.

Guards the poc3 perf chantier: batch_eat() replaces the O(pop x live apples)
per-agent Python loop (agent.eat(), 29% of the tick per the poc3 audit) with
one NumPy pass, but must resolve competing agents (two agents in reach of the
same apple) exactly like the sequential loop does — smallest population index
wins, since eat() never reads another agent's position. Any drift here is a
silent behavioural regression, not just a slowdown.
"""

from __future__ import annotations

from random import Random

from src.agent import Agent, batch_eat
from src.apple import Apple
from src.config import SimConfig
from src.environment import Environment
from src.genome import Genome, network_layer_shapes


def _make_population(cfg, env, positions, energy=1.0):
    genome = Genome.new_random(cfg.genome, network_layer_shapes(cfg.network), Random(0))
    agents = []
    for i, (x, y) in enumerate(positions):
        agent = Agent(genome.clone(), (x, y), cfg, env, Random(i))
        agent.energy = energy
        agents.append(agent)
    return agents


def _contested_scenario(cfg):
    """5 agents, 5 apples: contested pairs, an isolated single-apple case, a
    double-apple case for one agent, and one apple nobody can reach."""
    reach = cfg.agent.radius + cfg.apple.radius
    agent_positions = [
        (100.0, 100.0),  # 0
        (100.0 + 0.5 * reach, 100.0),  # 1 — close enough to contest with 0
        (300.0, 100.0),  # 2 — isolated
        (500.0, 100.0),  # 3
        (500.0 + 0.5 * reach, 100.0),  # 4 — close enough to contest with 3
    ]
    apple_positions = [
        (100.0 + 0.1 * reach, 100.0),  # A: in reach of 0 AND 1 -> 0 wins
        (300.0 + 0.1 * reach, 100.0),  # B: only agent 2 in reach
        (300.0 - 0.2 * reach, 100.0),  # C: also only agent 2 -> 2 eats two apples
        (300.0 + 5.0 * reach, 300.0),  # D: nobody in reach -> uneaten
        (500.0 - 0.1 * reach, 100.0),  # E: in reach of 3 AND 4 -> 3 wins
    ]
    return agent_positions, apple_positions


def test_batch_eat_matches_sequential_loop():
    cfg = SimConfig.from_yaml("config/default.yaml")
    agent_positions, apple_positions = _contested_scenario(cfg)

    # --- Path 1: sequential Agent.eat() per agent, population order ---
    env_seq = Environment(cfg, Random(1))
    env_seq.apples[:] = [Apple(x, y) for x, y in apple_positions]
    agents_seq = _make_population(cfg, env_seq, agent_positions)
    eaten_seq = [agent.eat() for agent in agents_seq]
    energies_seq = [agent.energy for agent in agents_seq]
    remaining_seq = {(a.x, a.y) for a in env_seq.apples}

    # --- Path 2: batched, identical starting state ---
    env_batch = Environment(cfg, Random(1))
    env_batch.apples[:] = [Apple(x, y) for x, y in apple_positions]
    agents_batch = _make_population(cfg, env_batch, agent_positions)
    eaten_batch = batch_eat(agents_batch, env_batch, cfg)
    energies_batch = [agent.energy for agent in agents_batch]
    remaining_batch = {(a.x, a.y) for a in env_batch.apples}

    assert energies_batch == energies_seq
    assert remaining_batch == remaining_seq
    assert [len(e) for e in eaten_batch] == [len(e) for e in eaten_seq]
    for won_seq, won_batch in zip(eaten_seq, eaten_batch):
        assert {(a.x, a.y) for a in won_seq} == {(a.x, a.y) for a in won_batch}

    # Sanity on the scenario itself (not just the two paths agreeing with
    # each other) — pin down the exact expected outcome. Agent 3 (smaller
    # index) wins the E/3-vs-4 contest, not agent 4.
    assert [len(e) for e in eaten_seq] == [1, 0, 2, 1, 0]


def test_batch_eat_caps_energy_at_max_like_sequential_loop():
    """An agent that wins multiple apples must still cap at max_energy,
    identically whether capped after each apple (sequential) or once (batched)."""
    cfg = SimConfig.from_yaml("config/default.yaml")
    reach = cfg.agent.radius + cfg.apple.radius
    apple_positions = [
        (100.0, 100.0),
        (100.0 + 0.1 * reach, 100.0),
        (100.0, 100.0 + 0.1 * reach),
    ]

    env_seq = Environment(cfg, Random(1))
    env_seq.apples[:] = [Apple(x, y) for x, y in apple_positions]
    agent_seq = _make_population(
        cfg, env_seq, [(100.0, 100.0)], energy=cfg.agent.max_energy - 0.1
    )[0]
    agent_seq.eat()

    env_batch = Environment(cfg, Random(1))
    env_batch.apples[:] = [Apple(x, y) for x, y in apple_positions]
    agent_batch = _make_population(
        cfg, env_batch, [(100.0, 100.0)], energy=cfg.agent.max_energy - 0.1
    )[0]
    batch_eat([agent_batch], env_batch, cfg)

    assert agent_batch.energy == agent_seq.energy == cfg.agent.max_energy


def test_batch_eat_no_apples_returns_empty_lists():
    cfg = SimConfig.from_yaml("config/default.yaml")
    env = Environment(cfg, Random(1))
    env.apples.clear()
    agents = _make_population(cfg, env, [(100.0, 100.0), (200.0, 200.0)])
    assert batch_eat(agents, env, cfg) == [[], []]


def test_batch_eat_empty_population_returns_empty_list():
    cfg = SimConfig.from_yaml("config/default.yaml")
    env = Environment(cfg, Random(1))
    assert not batch_eat([], env, cfg)


def test_batch_eat_matches_sequential_over_an_evolved_tick():
    """Same equivalence check but on realistic post-tick positions/apple
    layout, not just the hand-crafted contested scenario."""
    cfg = SimConfig.from_yaml("config/default.yaml")
    from src.simulation import Simulation  # local import: avoid a module cycle

    sim = Simulation(cfg, Random(7))
    for _ in range(50):
        sim.tick()
    assert sim.population, "population went extinct — cannot compare eating"

    apple_positions = [(a.x, a.y) for a in sim.env.apples]
    agent_positions = [(a.x, a.y) for a in sim.population]
    agent_energies = [a.energy for a in sim.population]

    env_seq = Environment(cfg, Random(1))
    env_seq.apples[:] = [Apple(x, y) for x, y in apple_positions]
    agents_seq = _make_population(cfg, env_seq, agent_positions)
    for agent, energy in zip(agents_seq, agent_energies):
        agent.energy = energy
    eaten_seq = [agent.eat() for agent in agents_seq]

    env_batch = Environment(cfg, Random(1))
    env_batch.apples[:] = [Apple(x, y) for x, y in apple_positions]
    agents_batch = _make_population(cfg, env_batch, agent_positions)
    for agent, energy in zip(agents_batch, agent_energies):
        agent.energy = energy
    eaten_batch = batch_eat(agents_batch, env_batch, cfg)

    assert [a.energy for a in agents_batch] == [a.energy for a in agents_seq]
    assert {(a.x, a.y) for a in env_batch.apples} == {
        (a.x, a.y) for a in env_seq.apples
    }
    for won_seq, won_batch in zip(eaten_seq, eaten_batch):
        assert {(a.x, a.y) for a in won_seq} == {(a.x, a.y) for a in won_batch}
