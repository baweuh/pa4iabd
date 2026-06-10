"""Simulation: the fixed-timestep driver tying population, world and logging.

Phase 6 assembles Phases 1-5 into a running world. Responsibilities:
- Spawn an initial population of agents with fresh fully-connected genomes.
- Advance the world one *tick* at a time (the atomic unit; the renderer of
  Phase 7 will call :meth:`tick` at a fixed cadence — invariant n°7, no Pygame
  here, no real-time sleeping in this module).
- Manage births, deaths and clean extinction (population 0 -> stop).
- Log metrics to CSV every ``logging.log_interval_ticks`` ticks and dump the
  best genome to JSON whenever the lifetime-apples record is beaten.

Invariants honoured here:
- n°1 — zero hardcoding: every number comes from ``SimConfig``.
- n°2 — energy is apple-equivalent per tick (delegated to ``Agent``/``Environment``).
- n°4 — each agent's network topology is sorted once at birth (in ``Agent.__init__``),
  never here.
- n°7 — the simulation never touches the renderer; ``tick`` is the unit it drives.

Per-tick orchestration (staged pipeline):
  1. perception + action + eating   (per living agent)
  2. metabolism + death marking      (per living agent)
  3. deferred apple respawns         (Environment.tick_respawns)
  4. reproduction                    (living agents, capped at population.max_size)
  5. record check + best-genome dump
  6. tick counter + periodic CSV row
"""

from __future__ import annotations

import csv
from pathlib import Path
from random import Random
from typing import TextIO

from src.agent import Agent
from src.config import SimConfig
from src.environment import Environment
from src.genome import TRACKER, Genome

CSV_HEADER = (
    "tick",
    "population",
    "food_available",
    "record_apples",
    "avg_lifespan",
    "total_reproductions",
    "avg_network_size",
)


class Simulation:
    """Owns the world, the population and the metric/genome outputs."""

    def __init__(self, config: SimConfig, rng: Random | None = None) -> None:
        self._config = config
        self._rng = rng if rng is not None else Random(config.simulation.seed)

        # A fresh innovation history per simulation keeps genome ids deterministic.
        TRACKER.reset()
        self.env = Environment(config, self._rng)

        self.tick_count: int = 0
        self.total_reproductions: int = 0
        self.record_apples: int = 0
        # Lifetime apples eaten, per living agent (drives record + best genome).
        self._apples_eaten: dict[Agent, int] = {}

        self.population: list[Agent] = [
            self._spawn_agent() for _ in range(config.population.initial_size)
        ]
        for agent in self.population:
            self._apples_eaten[agent] = 0

        self._csv_file: TextIO | None = None
        self._csv_writer = None

    # ------------------------------------------------------------------ #
    # Population helpers
    # ------------------------------------------------------------------ #
    def _spawn_agent(self) -> Agent:
        """Create one agent with a fresh genome at a random safe-zone position."""
        genome = Genome.new_fully_connected(
            self._config.genome,
            self._config.network.num_inputs,
            self._config.network.num_outputs,
            self._rng,
        )
        return Agent(
            genome, self._safe_spawn_position(), self._config, self.env, self._rng
        )

    def _safe_spawn_position(self) -> tuple[float, float]:
        """Uniform draw inside the safe zone, inset by the agent radius."""
        zw = self._config.penalty_zone.width
        r = self._config.agent.radius
        x = self._rng.uniform(zw + r, self._config.world.width - zw - r)
        y = self._rng.uniform(zw + r, self._config.world.height - zw - r)
        return (x, y)

    # ------------------------------------------------------------------ #
    # Read-only views
    # ------------------------------------------------------------------ #
    @property
    def population_size(self) -> int:
        """Number of living agents."""
        return len(self.population)

    @property
    def food_available(self) -> int:
        """Live apples currently on the board (pending respawns excluded)."""
        return len(self.env.apples)

    @property
    def is_extinct(self) -> bool:
        """True once no agents remain."""
        return not self.population

    # ------------------------------------------------------------------ #
    # The loop
    # ------------------------------------------------------------------ #
    def tick(self) -> None:
        """Advance the world by exactly one tick (staged pipeline)."""
        # Stage 1 — perception, action, eating.
        for agent in self.population:
            agent.age += 1
            vx, vy = agent.activate()
            agent.move(vx, vy)
            self._apples_eaten[agent] += agent.eat()

        # Stage 2 — metabolism and death marking.
        for agent in self.population:
            agent.metabolize()
            if agent.is_dead():
                agent.alive = False

        # Stage 3 — deferred apple respawns (step 8).
        self.env.tick_respawns(self._rng)

        # Stage 4 — reproduction, then recompose the population.
        max_size = self._config.population.max_size
        children: list[Agent] = []
        survivors = sum(1 for a in self.population if a.alive)
        for agent in self.population:
            if not agent.alive:
                continue
            if survivors + len(children) >= max_size:
                break
            if agent.can_reproduce():
                child = agent.reproduce()
                self._apples_eaten[child] = 0
                children.append(child)
                self.total_reproductions += 1

        dead = [a for a in self.population if not a.alive]
        for agent in dead:
            del self._apples_eaten[agent]
        self.population = [a for a in self.population if a.alive] + children

        # Stage 5 — record check + best-genome dump.
        self._update_record()

        # Stage 6 — tick counter + periodic logging.
        self.tick_count += 1
        if self.tick_count % self._config.logging.log_interval_ticks == 0:
            self._log_row()

    def run(self) -> None:
        """Drive ticks headless until extinction or ``simulation.max_ticks``.

        ``max_ticks == 0`` means run until the population dies out. No real-time
        pacing here: ``ticks_per_second`` belongs to the renderer (Phase 7).
        """
        max_ticks = self._config.simulation.max_ticks
        self._open_csv()
        try:
            while not self.is_extinct:
                if max_ticks and self.tick_count >= max_ticks:
                    break
                self.tick()
        finally:
            self._close_csv()

    # ------------------------------------------------------------------ #
    # Record / best genome
    # ------------------------------------------------------------------ #
    def _update_record(self) -> None:
        """Dump the genome of any agent whose lifetime apples beat the record."""
        if not self._apples_eaten:
            return
        best_agent = max(self._apples_eaten, key=self._apples_eaten.__getitem__)
        best = self._apples_eaten[best_agent]
        if best > self.record_apples:
            self.record_apples = best
            self._save_best_genome(best_agent.genome)

    def _save_best_genome(self, genome: Genome) -> None:
        path = Path(self._config.logging.best_genome_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(genome.to_json(), encoding="utf-8")

    # ------------------------------------------------------------------ #
    # CSV logging
    # ------------------------------------------------------------------ #
    def _open_csv(self) -> None:
        path = Path(self._config.logging.csv_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Kept open across the whole run; closed in _close_csv (run()'s finally).
        # pylint: disable=consider-using-with
        self._csv_file = path.open("w", encoding="utf-8", newline="")
        self._csv_writer = csv.writer(self._csv_file)
        self._csv_writer.writerow(CSV_HEADER)

    def _close_csv(self) -> None:
        if self._csv_file is not None:
            self._csv_file.close()
            self._csv_file = None
            self._csv_writer = None

    def _log_row(self) -> None:
        if self._csv_writer is None:
            return
        self._csv_writer.writerow(
            (
                self.tick_count,
                self.population_size,
                self.food_available,
                self.record_apples,
                f"{self._avg_lifespan():.6f}",
                self.total_reproductions,
                f"{self._avg_network_size():.6f}",
            )
        )

    # ------------------------------------------------------------------ #
    # Metrics
    # ------------------------------------------------------------------ #
    def _avg_lifespan(self) -> float:
        """Mean age of the living population (0.0 when empty)."""
        if not self.population:
            return 0.0
        return sum(a.age for a in self.population) / len(self.population)

    def _avg_network_size(self) -> float:
        """Mean (#nodes + #enabled connections) per living genome (0.0 if empty)."""
        if not self.population:
            return 0.0
        total = 0
        for agent in self.population:
            genome = agent.genome
            enabled = sum(1 for c in genome.connections if c.enabled)
            total += len(genome.nodes) + enabled
        return total / len(self.population)
