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
from collections import Counter, deque
from datetime import datetime
from pathlib import Path
from random import Random
from typing import Callable, TextIO

import numpy as np

from src.agent import Agent, batch_sense
from src.apple import Apple
from src.config import SimConfig
from src.environment import Environment
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
    steer_score,
)
from src.novelty import population_novelty
from src.genome import TRACKER, Genome
from src.speciation import (
    assign_species,
    compatibility_distance,
    count_species,
    mean_pairwise_distance,
)

CSV_HEADER = (
    "tick",
    "population",
    "food_available",
    "record_apples",
    "avg_lifespan",
    "total_reproductions",
    "avg_network_size",
    # Evolutionary observability (appended; earlier column indices are stable).
    "max_generation",
    "mean_generation",
    "species_count",
    "mean_genetic_distance",
    "mean_forage_rate",
    "max_forage_rate",
    # Extended diagnostics (poc2.4, 2026-07-15; appended, earlier indices
    # stable) — all observational, see src.diagnostics and DiagnosticsConfig.
    "mean_steer_score",
    "forager_pct",
    "mean_hidden_nodes",
    "mean_novelty_score",
    "agent_density_global",
    "apple_density_global",
    "agent_density_local_mean",
    "apple_density_local_mean",
    "capture_adjacent_pct",
    "capture_directed_pct",
    "capture_undirected_pct",
    "apples_eaten_per_tick",
    "effective_population_size",
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
        # Tick of the last O(pop²) novelty rescoring (-1 = never). Gates the
        # periodic recompute in _add_novelty_bonus (novelty.recompute_interval).
        self._last_novelty_tick: int = -1
        # Persistent pool of past behaviour descriptors (novelty.archive_enabled
        # only; FIFO-capped at archive_max_size). See _refresh_novelty_scores.
        self._novelty_archive: deque[np.ndarray] = deque(
            maxlen=config.novelty.archive_max_size
        )
        # Lifetime apples eaten, per living agent (drives record + best genome).
        self._apples_eaten: dict[Agent, int] = {}
        # Unspent reproduction credit (apples eaten minus apples spent on offspring).
        # Only used when agent.apples_per_offspring > 0 (structural foraging-coupled
        # fecundity); mirrors the lifecycle of _apples_eaten.
        self._repro_credit: dict[Agent, float] = {}
        # Consecutive ticks each agent has held credit >= apples_per_offspring, for
        # the minimal-criterion reproduction gate (agent.reproduction_min_ticks).
        # Resets to 0 whenever credit drops below the threshold or after a birth.
        # Only tracked when the gate is active; mirrors _repro_credit's lifecycle.
        self._credit_streak: dict[Agent, int] = {}
        # Island id (0..num_islands-1) each agent belongs to (island model,
        # population.num_islands). A child inherits its parent's island; an
        # elite clone inherits the record holder's. Always populated, even
        # when num_islands == 1 (everyone is island 0) — mirrors the other
        # per-agent bookkeeping dicts' lifecycle.
        self._island: dict[Agent, int] = {}
        # Bounded per-agent (tick, x, y, heading) history, used ONLY to find a
        # capture's reference point (src.diagnostics.classify_capture) —
        # diagnostics, never read by simulation logic. Length derived from
        # config (invariant n°1): enough ticks to cross the sensing range once.
        self._capture_lookback: int = capture_lookback_ticks(
            config.sensors, config.agent
        )
        self._position_history: dict[Agent, deque[tuple[int, float, float, float]]] = {}
        # Population-level capture-classification counts, accumulated since
        # the last CSV row and reset there (_log_row) — see _classify_captures.
        self._capture_counts: dict[str, int] = {ADJACENT: 0, DIRECTED: 0, UNDIRECTED: 0}
        # Local agent/apple density SAMPLED ONLY at capture events (not every
        # tick), accumulated since the last CSV row and reset there.
        self._local_agent_density_samples: list[int] = []
        self._local_apple_density_samples: list[int] = []
        # Apples eaten since the last CSV row, reset there (apples_eaten_per_tick).
        self._apples_eaten_interval: int = 0
        # (tick, parent) for every birth, pruned to diagnostics.ne_window_ticks
        # at each CSV row — feeds effective_population_size (N_e). Independent
        # of agent liveness: a dead parent's births simply age out of the
        # window like anyone else's (see src.diagnostics.effective_population_size).
        self._birth_events: deque[tuple[int, Agent]] = deque()
        # Timestamp shared by all files produced by this run (YYYY-MM-DD_HHMMSS).
        # One folder per run under the configured log directory.
        self._run_id: str = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        # Monotonic counter for best-agent files within this run.
        self._best_agent_counter: int = 0

        self.population: list[Agent] = [
            self._spawn_agent() for _ in range(config.population.initial_size)
        ]
        n_islands = config.population.num_islands
        for i, agent in enumerate(self.population):
            self._apples_eaten[agent] = 0
            self._repro_credit[agent] = 0.0
            self._credit_streak[agent] = 0
            self._island[agent] = i % n_islands  # round-robin founders
            self._position_history[agent] = deque(maxlen=self._capture_lookback + 1)

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

    def _island_capacities(self) -> list[int]:
        """Per-island slot budget: ``max_size`` split as evenly as possible.

        The first ``max_size % num_islands`` islands absorb the one-off
        remainder, so capacities always sum to exactly ``max_size``. With
        ``num_islands == 1`` this is ``[max_size]`` — the legacy global cap.
        """
        n = self._config.population.num_islands
        base, extra = divmod(self._config.population.max_size, n)
        return [base + (1 if i < extra else 0) for i in range(n)]

    # ------------------------------------------------------------------ #
    # Read-only views
    # ------------------------------------------------------------------ #
    @property
    def run_id(self) -> str:
        """Timestamp string that identifies this run (used to name log files)."""
        return self._run_id

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
        # Stage 0 — snapshot start-of-tick position/heading (diagnostics only:
        # the reference point capture classification needs, see
        # _classify_captures). Taken BEFORE movement, so "was the agent
        # already here" always means "at the start of this tick", never
        # mid-tick. Every living agent already has a deque (founders in
        # __init__, children in _birth, elites in _inject_elite).
        for agent in self.population:
            self._position_history[agent].append(
                (self.tick_count, agent.x, agent.y, agent.heading)
            )

        # Stage 1 — perception, action, eating.
        # "Freeze then perceive": the whole population's senses are computed in a
        # single NumPy pass against the tick-start world (batch_sense), then each
        # agent acts and eats in index order. Agents never sense one another, so
        # the only behavioural delta vs a per-agent perceive-then-eat loop is that
        # an agent may perceive an apple a lower-index agent eats the same tick.
        # Perception is 57% of the tick; batching it is the poc2.4 perf win.
        senses = batch_sense(self.population, self.env, self._config)
        for agent, agent_senses in zip(self.population, senses):
            agent.age += 1
            vx, vy = agent.decide(agent_senses)
            agent.move(vx, vy)
            eaten_apples = agent.eat()
            eaten = len(eaten_apples)
            self._apples_eaten[agent] += eaten
            agent.apples_eaten += eaten
            self._repro_credit[agent] += eaten
            if eaten_apples:
                self._apples_eaten_interval += eaten
                self._classify_captures(agent, eaten_apples)

        # Stage 2 — metabolism and death marking.
        for agent in self.population:
            agent.metabolize()
            if agent.is_dead():
                agent.alive = False

        # Stage 3 — deferred apple respawns (step 8).
        self.env.tick_respawns(self._rng, self.tick_count + 1)

        # Stage 4 — reproduction, then recompose the population.
        # Births are capped by free slots under ``population.max_size``, split
        # per island (see :meth:`_reproduce`/:meth:`_island_capacities`; 1
        # island, the default, collapses to the legacy single pool). Within a
        # pool, scarce slots go to the highest-priority eligible agents first
        # (energy or foraging credit, optionally species-shared /
        # novelty-boosted, see :meth:`_priority_fn`) — that is the selection
        # pressure. Stable sort keeps the run deterministic on ties.
        survivors = [a for a in self.population if a.alive]
        total_slots = self._config.population.max_size - len(survivors)
        children = self._reproduce(survivors, total_slots)

        if self._config.population.num_islands > 1:
            self._migrate(survivors)

        dead = [a for a in self.population if not a.alive]
        for agent in dead:
            del self._apples_eaten[agent]
            del self._repro_credit[agent]
            del self._credit_streak[agent]
            del self._island[agent]
            del self._position_history[agent]
        self.population = [a for a in self.population if a.alive] + children

        # Stage 5 — record check + best-genome dump.
        self._update_record()

        # Stage 6 — tick counter + periodic logging.
        self.tick_count += 1
        if self.tick_count % self._config.logging.log_interval_ticks == 0:
            self._log_row()

    def _reproduce(self, survivors: list[Agent], total_slots: int) -> list[Agent]:
        """Stage 4 body: fill up to ``total_slots`` children, split per island.

        Each island is a fully separate competitive pool (its own
        eligible/priority ranking, its own mating pool via the survivors
        subset handed to ``_birth``) — a dominant lineage in one island
        cannot drain another island's slots. 1 island (default, see
        :meth:`_island_capacities`) collapses to the legacy single pool,
        byte-for-byte unchanged.
        """
        novelty_on = self._config.novelty.enabled and self._config.novelty.weight > 0.0
        if novelty_on and total_slots > 0 and len(survivors) > 1:
            # Refreshed ONCE per tick, over the WHOLE population, regardless of
            # island count: the k-NN neighbourhood must span every island, and
            # this keeps the recompute_interval cadence identical to the
            # legacy (single-island) timing. Per-island calls below then only
            # read the cached agent.novelty_score (see _add_novelty_bonus).
            self._maybe_refresh_novelty(survivors)

        children: list[Agent] = []
        if total_slots <= 0:
            return children
        per_child = self._config.agent.apples_per_offspring
        for island_id, capacity in enumerate(self._island_capacities()):
            island_survivors = [a for a in survivors if self._island[a] == island_id]
            slots = capacity - len(island_survivors)
            if slots <= 0:
                continue
            if per_child > 0.0:
                island_children = self._reproduce_by_foraging(
                    island_survivors, slots, per_child
                )
            else:
                island_children = self._reproduce_by_energy(island_survivors, slots)
            children.extend(island_children)
        return children

    def _classify_captures(self, agent: Agent, eaten: list[Apple]) -> None:
        """Classify ``agent``'s captures this tick (diagnostics only).

        For each apple, finds the earliest entry in ``agent``'s bounded
        position history at or after the apple's own ``spawn_tick`` (falling
        back to the oldest entry the history holds, if the apple has been
        alive longer than the whole lookback window — same heuristic as
        ``tools/apple_capture_probe.py``) and classifies via
        ``src.diagnostics.classify_capture``. Updates the population-level
        interval counters (:attr:`_capture_counts`, read and reset by
        :meth:`_log_row`) and the per-agent lifetime counters
        (``Agent.directed_captures``/``fortuitous_captures``), and samples
        local agent/apple density AT the capture (only here — an event, not
        every tick, see ``diagnostics.local_density_radius``).
        """
        cfg = self._config.diagnostics
        reach = self._config.agent.radius + self._config.apple.radius
        history = self._position_history[agent]
        default_ref = (self.tick_count, agent.x, agent.y, agent.heading)
        for apple in eaten:
            ref = history[0] if history else default_ref
            for entry in history:
                if entry[0] >= apple.spawn_tick:
                    ref = entry
                    break
            _, ref_x, ref_y, ref_h = ref
            category = classify_capture(
                apple.x, apple.y, ref_x, ref_y, ref_h, reach, cfg
            )
            self._capture_counts[category] += 1
            if category == DIRECTED:
                agent.directed_captures += 1
            else:
                agent.fortuitous_captures += 1
            self._local_agent_density_samples.append(
                local_agent_density(agent, self.population, cfg.local_density_radius)
            )
            self._local_apple_density_samples.append(
                local_apple_density(apple, self.env.apples, cfg.local_density_radius)
            )

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
    # Reproduction strategies (selected by agent.apples_per_offspring)
    # ------------------------------------------------------------------ #
    def _reproduce_by_energy(self, survivors: list[Agent], slots: int) -> list[Agent]:
        """Legacy reproduction: energy-threshold eligibility, priority by energy.

        Highest-energy eligible agents fill the scarce slots first (species-shared
        when ``speciation.fitness_sharing`` is on, see :meth:`_priority_fn`);
        fecundity per agent is bounded by how many times its energy exceeds the
        threshold, optionally softened by ``agent.max_children_per_tick`` (flat
        per-agent cap) and/or ``agent.reproduction_round_robin`` (breadth-first
        distribution) — see :class:`~src.config.AgentConfig` and
        :meth:`_round_robin_fill`.
        """
        cap = self._config.agent.max_children_per_tick
        priority = self._priority_fn(survivors, lambda a: a.energy)
        eligible = sorted(
            (a for a in survivors if a.can_reproduce()), key=priority, reverse=True
        )

        if self._config.agent.reproduction_round_robin:

            def step(agent: Agent) -> Agent | None:
                if not agent.can_reproduce():
                    return None
                return self._birth(agent, survivors)

            return self._round_robin_fill(eligible, slots, cap, step)

        children: list[Agent] = []
        for agent in eligible:
            born = 0
            while (
                agent.can_reproduce()
                and len(children) < slots
                and (cap == 0 or born < cap)
            ):
                children.append(self._birth(agent, survivors))
                born += 1
            if len(children) >= slots:
                break
        return children

    def _round_robin_fill(
        self,
        eligible: list[Agent],
        slots: int,
        cap: int,
        step: Callable[[Agent], "Agent | None"],
    ) -> list[Agent]:
        """Distribute reproduction slots breadth-first across eligible agents.

        Truncation softening (research-roadmap chantier n°2; Corus et al. 2021
        on truncation-driven diversity loss). One PASS gives at most one child
        per agent, in priority order, before any agent gets a second — so a
        dominant agent can no longer claim every open slot before the runner-up
        is even considered. ``step`` performs one birth attempt for an agent
        (mutating its energy/credit as a side effect) and returns the child, or
        ``None`` once the agent no longer qualifies. ``cap`` (0 = unbounded)
        additionally limits total children per agent across all passes.
        """
        children: list[Agent] = []
        counts: dict[Agent, int] = {}
        remaining = list(eligible)
        while remaining and len(children) < slots:
            next_round: list[Agent] = []
            for agent in remaining:
                if len(children) >= slots:
                    break
                if cap and counts.get(agent, 0) >= cap:
                    continue
                child = step(agent)
                if child is None:
                    continue
                children.append(child)
                counts[agent] = counts.get(agent, 0) + 1
                next_round.append(agent)
            if not next_round:
                break
            remaining = next_round
        return children

    def _reproduce_by_foraging(
        self, survivors: list[Agent], slots: int, per_child: float
    ) -> list[Agent]:
        """Structural reproduction: fecundity driven by CUMULATIVE foraging.

        Each agent banks +1 reproduction credit per apple eaten and spends
        ``per_child`` credit per offspring, so lifetime offspring ≈ apples_eaten /
        per_child — reproductive success scales linearly with foraging competence,
        decoupled from the instantaneous-energy cap. At the cap the best-fed
        foragers fill the slots first (priority by unspent credit, species-shared
        when ``speciation.fitness_sharing`` is on, see :meth:`_priority_fn`). The
        parent still pays ``reproduction_cost`` energy per child (a birth is not
        free) and stops once out of energy, so a starving forager cannot cash in
        credit it can't fuel.

        ``agent.reproduction_min_ticks`` (0 = off, legacy) adds a minimal-criterion
        gate: an agent must have HELD credit >= ``per_child`` for that many
        consecutive ticks before it may reproduce, and then produces exactly ONE
        child (its streak resets — a refractory period). The credit streak is
        refreshed here every reproduction tick for all survivors. See
        :meth:`_refresh_credit_streaks`.

        ``agent.max_children_per_tick`` / ``agent.reproduction_round_robin``
        (both off = legacy) soften the greedy per-agent while-loop on the
        ``min_ticks == 0`` path only — see :class:`~src.config.AgentConfig` and
        :meth:`_round_robin_fill`. No-op once ``min_ticks > 0``, which already
        limits every agent to one child per tick.
        """
        min_ticks = self._config.agent.reproduction_min_ticks
        cap = self._config.agent.max_children_per_tick
        if min_ticks > 0:
            self._refresh_credit_streaks(survivors, per_child)

        priority = self._priority_fn(survivors, lambda a: self._repro_credit[a])
        eligible = sorted(
            (
                a
                for a in survivors
                if self._repro_credit[a] >= per_child
                and self._credit_streak[a] >= min_ticks
            ),
            key=priority,
            reverse=True,
        )

        if min_ticks == 0 and self._config.agent.reproduction_round_robin:

            def step(agent: Agent) -> Agent | None:
                if self._repro_credit[agent] < per_child or agent.energy <= 0.0:
                    return None
                self._repro_credit[agent] -= per_child
                return self._birth(agent, survivors)

            return self._round_robin_fill(eligible, slots, cap, step)

        children: list[Agent] = []
        for agent in eligible:
            if len(children) >= slots:
                break
            if min_ticks > 0:
                # Minimal-criterion path: one child per qualifying agent per tick,
                # then the streak resets (refractory period, not a per-tick refill).
                if agent.energy > 0.0:
                    self._repro_credit[agent] -= per_child
                    self._credit_streak[agent] = 0
                    children.append(self._birth(agent, survivors))
                continue
            born = 0
            while (
                self._repro_credit[agent] >= per_child
                and agent.energy > 0.0
                and len(children) < slots
                and (cap == 0 or born < cap)
            ):
                born += 1
                self._repro_credit[agent] -= per_child
                children.append(self._birth(agent, survivors))
        return children

    def _refresh_credit_streaks(self, survivors: list[Agent], per_child: float) -> None:
        """Advance each survivor's sustained-credit streak by one tick.

        The streak counts consecutive reproduction ticks with credit at or above
        ``per_child``; it resets to 0 the moment credit falls below that. Backs the
        minimal-criterion gate in :meth:`_reproduce_by_foraging`.
        """
        for agent in survivors:
            if self._repro_credit[agent] >= per_child:
                self._credit_streak[agent] += 1
            else:
                self._credit_streak[agent] = 0

    def _migrate(self, survivors: list[Agent]) -> None:
        """Ring migration: move a few agents per island to the next island.

        Every ``population.migration_interval_ticks`` (same 1-indexed cadence
        as ``logging.log_interval_ticks`` — the tick this call is completing
        is ``tick_count + 1``), up to ``migration_count`` random survivors per
        island step to ``(island + 1) % num_islands`` — bounded gene flow
        around a fixed ring, so islands stay otherwise fully separate
        competitive pools (see the reproduction loop in :meth:`tick`) between
        migrations. Never called when ``num_islands == 1`` (no-op
        destination, would only burn RNG draws for nothing).
        """
        cfg = self._config.population
        if (self.tick_count + 1) % cfg.migration_interval_ticks != 0:
            return
        by_island: dict[int, list[Agent]] = {i: [] for i in range(cfg.num_islands)}
        for agent in survivors:
            by_island[self._island[agent]].append(agent)
        for island_id, members in by_island.items():
            if not members:
                continue
            movers = self._rng.sample(members, min(cfg.migration_count, len(members)))
            for agent in movers:
                self._island[agent] = (island_id + 1) % cfg.num_islands

    def _priority_fn(
        self, survivors: list[Agent], raw: Callable[[Agent], float]
    ) -> Callable[[Agent], float]:
        """Reproduction-priority function, optionally modified by two mechanisms.

        Both off (default): returns ``raw`` unchanged — zero extra cost, legacy
        behaviour. The two modifiers compose (either, both, or neither):

        - ``speciation.fitness_sharing`` (REDUCER, falsified): divides each raw
          value by the agent's NEAT species size (``f'_i = f_i / |species_i|``,
          Stanley & Miikkulainen 2002), so a dominant lineage no longer autowins
          scarce slots on raw fitness alone.
        - ``novelty.enabled`` (ADDITIVE): adds a bounded bonus for behaviourally
          novel agents (see :meth:`_add_novelty_bonus`), on top of the base value
          — never penalising, matching the only pattern that has worked here.
        """
        novelty_on = self._config.novelty.enabled and self._config.novelty.weight > 0.0
        if not self._config.speciation.fitness_sharing and not novelty_on:
            return raw

        if self._config.speciation.fitness_sharing:
            species_ids = assign_species(
                [a.genome for a in survivors], self._config.speciation
            )
            sizes = Counter(species_ids)
            values = {
                agent: raw(agent) / sizes[species_id]
                for agent, species_id in zip(survivors, species_ids)
            }
        else:
            values = {agent: raw(agent) for agent in survivors}

        if novelty_on and len(survivors) > 1:
            self._add_novelty_bonus(survivors, values)

        return values.__getitem__

    def _maybe_refresh_novelty(self, survivors: list[Agent]) -> None:
        """Rescore novelty for the whole population, gated by the interval.

        Called ONCE per tick from :meth:`tick` (before the per-island
        reproduction loop, not from inside :meth:`_add_novelty_bonus`) so the
        O(pop²) pass and its cadence are identical whether there is 1 island
        or many — :meth:`_add_novelty_bonus` only ever reads the cached
        ``agent.novelty_score`` it leaves behind.
        """
        cfg = self._config.novelty
        if (
            self._last_novelty_tick < 0
            or self.tick_count - self._last_novelty_tick >= cfg.recompute_interval
        ):
            self._refresh_novelty_scores(survivors)

    def _add_novelty_bonus(
        self, survivors: list[Agent], values: dict[Agent, float]
    ) -> None:
        """Add a bounded behavioural-novelty bonus to ``values`` in place.

        Novelty search (Lehman & Stanley 2011) as an ADDITIVE term: the most
        novel agent gets up to ``weight × mean(base value)`` extra priority, the
        least novel gets nothing (min-max normalised novelty ∈ [0, 1]). Scale-free
        — the bonus tracks whatever fitness scale (energy or foraging credit) is
        in play. ``survivors`` here may be an island subset: the bonus is then
        relative to island peers only, but the underlying ``novelty_score`` was
        computed against the whole population (see :meth:`_maybe_refresh_novelty`).

        Self-refreshing: applies the same gate as :meth:`_maybe_refresh_novelty`
        (harmless to repeat — ``tick`` already refreshed once, globally, before
        the per-island loop, so ``self._last_novelty_tick`` is already current
        and this is a no-op there; kept here too so calling this — or
        :meth:`_priority_fn` — directly, as the tests do, is still
        self-sufficient).
        """
        cfg = self._config.novelty
        if (
            self._last_novelty_tick < 0
            or self.tick_count - self._last_novelty_tick >= cfg.recompute_interval
        ):
            self._refresh_novelty_scores(survivors)

        scores = np.fromiter(
            (agent.novelty_score for agent in survivors), np.float64, len(survivors)
        )
        low, high = float(scores.min()), float(scores.max())
        span = high - low
        mean_base = sum(values.values()) / len(values)
        scale = cfg.weight * mean_base
        for i, agent in enumerate(survivors):
            normalised = (scores[i] - low) / span if span > 1e-12 else 0.0
            values[agent] += scale * normalised

    def _refresh_novelty_scores(self, survivors: list[Agent]) -> None:
        """Rescore every survivor's raw novelty (mean k-NN behavioural distance).

        The O(pop²) pass; cached on each agent (``novelty_score``) and reused by
        :meth:`_add_novelty_bonus` until the next refresh. Newborns keep 0.0 until
        rescored — a negligible, few-tick omission of their bonus.

        With ``novelty.archive_enabled``, agents are also measured novel
        against a persistent archive of past behaviours (:attr:`_novelty_archive`),
        widening the neighbourhood beyond whatever the live population currently
        offers. Each scored agent is then independently archived with
        probability ``archive_prob`` (Lehman & Stanley 2011's random-injection
        scheme) — the archive itself is never scored, only added to.
        """
        cfg = self._config.novelty
        descriptors = np.array([agent.behavior_descriptor for agent in survivors])
        archive = (
            np.array(self._novelty_archive)
            if cfg.archive_enabled and self._novelty_archive
            else None
        )
        novelty = population_novelty(descriptors, cfg.neighbors, archive)
        for agent, score in zip(survivors, novelty):
            agent.novelty_score = float(score)
        if cfg.archive_enabled:
            for descriptor in descriptors:
                if self._rng.random() < cfg.archive_prob:
                    self._novelty_archive.append(descriptor)
        self._last_novelty_tick = self.tick_count

    def _birth(self, parent: Agent, pool: list[Agent]) -> Agent:
        """Spawn one child from ``parent``, register its bookkeeping, count it.

        When crossover is enabled (``genome.crossover_rate > 0``) the birth is
        sexual with probability ``crossover_rate``, mating ``parent`` with a
        compatible partner drawn from ``pool`` (see :meth:`_pick_mate`).
        """
        child = parent.reproduce(self._pick_mate(parent, pool))
        self._apples_eaten[child] = 0
        self._repro_credit[child] = 0.0
        self._credit_streak[child] = 0
        self._island[child] = self._island[parent]
        self._position_history[child] = deque(maxlen=self._capture_lookback + 1)
        self._birth_events.append((self.tick_count, parent))
        self.total_reproductions += 1
        return child

    def _pick_mate(self, parent: Agent, pool: list[Agent]) -> Agent | None:
        """Return an intra-species mate for ``parent``, or ``None`` for asexual.

        With probability ``genome.crossover_rate`` we draw one random other agent
        and accept it only if it is within the speciation ``compatibility_threshold``
        of ``parent`` (mating stays within a species); otherwise the birth falls
        back to asexual cloning. A single draw keeps this O(genome) per birth.
        """
        rate = self._config.genome.crossover_rate
        if rate <= 0.0 or len(pool) < 2 or self._rng.random() >= rate:
            return None
        mate = self._rng.choice(pool)
        if mate is parent:
            return None
        distance = compatibility_distance(
            parent.genome, mate.genome, self._config.speciation
        )
        if distance < self._config.speciation.compatibility_threshold:
            return mate
        return None

    # ------------------------------------------------------------------ #
    # Record / best genome
    # ------------------------------------------------------------------ #
    def _update_record(self) -> None:
        """Dump + re-inject the genome when lifetime apples beat the record."""
        if not self._apples_eaten:
            return
        best_agent = max(self._apples_eaten, key=self._apples_eaten.__getitem__)
        best = self._apples_eaten[best_agent]
        if best > self.record_apples:
            self.record_apples = best
            self._save_best_genome(best_agent.genome)
            self._inject_elite(best_agent.genome, self._island[best_agent])

    def _inject_elite(self, genome: Genome, island: int) -> None:
        """Spawn one unmutated clone of the record genome into ``island`` if a
        slot is available there.

        Elite injection keeps the best controller alive in the population when it
        would otherwise be lost by chance (the original bearer can die of old age
        or starvation before it reproduces). The clone starts fresh (initial
        energy, random position, no mutation applied) so it must compete. The
        capacity check is per-island (see :meth:`_island_capacities`) —
        identical to the old global ``max_size`` check when ``num_islands == 1``.
        """
        capacity = self._island_capacities()[island]
        occupied = sum(1 for a in self.population if self._island[a] == island)
        if occupied >= capacity:
            return
        elite = Agent(
            genome.clone(),
            self._safe_spawn_position(),
            self._config,
            self.env,
            self._rng,
        )
        self.population.append(elite)
        self._island[elite] = island
        self._apples_eaten[elite] = 0
        self._repro_credit[elite] = 0.0
        self._credit_streak[elite] = 0
        self._position_history[elite] = deque(maxlen=self._capture_lookback + 1)

    def _run_dir(self) -> Path:
        """Return (and create) the per-run log folder: logs/<run_id>/."""
        base = Path(self._config.logging.csv_path)
        folder = base.parent / self._run_id
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _save_best_genome(self, genome: Genome) -> None:
        """Dump the new record genome: one archive copy + the stable latest file.

        The history lives in ``best_agents/`` (one file per record); the file
        named by ``logging.best_genome_path`` in the run folder is overwritten
        each time so the current best is always at a predictable path.
        """
        self._best_agent_counter += 1
        payload = genome.to_json()
        folder = self._run_dir() / "best_agents"
        folder.mkdir(exist_ok=True)
        name = f"agent_{self._best_agent_counter:03d}_record_{self.record_apples}.json"
        (folder / name).write_text(payload, encoding="utf-8")
        latest = self._run_dir() / Path(self._config.logging.best_genome_path).name
        latest.write_text(payload, encoding="utf-8")

    # ------------------------------------------------------------------ #
    # CSV logging
    # ------------------------------------------------------------------ #
    def open_csv_logger(self) -> None:
        """Open the metrics CSV (header written). Pair with close_csv_logger().

        For manual headless loops (``main.py``) that drive :meth:`tick` directly
        and still want CSV output; :meth:`run` uses the private path internally.
        """
        self._open_csv()

    def close_csv_logger(self) -> None:
        """Flush and close the metrics CSV opened by :meth:`open_csv_logger`."""
        self._close_csv()

    def _open_csv(self) -> None:
        base = Path(self._config.logging.csv_path)
        path = self._run_dir() / base.name
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
        generations = [a.generation for a in self.population]
        forage_rates = self._forage_rates()
        genomes = [a.genome for a in self.population]
        mean_generation = _mean(generations)
        mean_forage = _mean(forage_rates)
        diag = self._diagnostics_row()
        self._csv_writer.writerow(
            (
                self.tick_count,
                self.population_size,
                self.food_available,
                self.record_apples,
                f"{self._avg_lifespan():.6f}",
                self.total_reproductions,
                f"{self._avg_network_size():.6f}",
                max(generations, default=0),
                f"{mean_generation:.6f}",
                count_species(genomes, self._config.speciation),
                f"{mean_pairwise_distance(genomes, self._config.speciation):.6f}",
                f"{mean_forage:.6f}",
                f"{max(forage_rates, default=0.0):.6f}",
            )
            + diag
        )

    def _diagnostics_row(self) -> tuple[str, ...]:
        """Extended diagnostics columns (see CSV_HEADER's tail, src.diagnostics).

        Snapshot metrics (steer_score, hidden nodes, novelty) are computed
        HERE ONLY — at the log tick, not every tick, same amortisation as the
        rest of ``_log_row`` — while capture/density/apples-eaten are the
        interval accumulators built up since the previous row (reset at the
        end of this method). All CSV-only: nothing here feeds back into the
        simulation.
        """
        cfg = self._config.diagnostics
        pop = self.population

        steer_scores = [steer_score(a.network, self._config.sensors) for a in pop]
        forager_pct = (
            100.0 * sum(1 for s in steer_scores if s > cfg.forager_threshold) / len(pop)
            if pop
            else 0.0
        )
        hidden_counts = [
            float(sum(1 for n in a.genome.nodes if n.node_type == "hidden"))
            for a in pop
        ]
        novelty_scores = [a.novelty_score for a in pop]

        world = self._config.world
        agent_density_global = global_density(len(pop), world.width, world.height)
        apple_density_global = global_density(
            self.food_available, world.width, world.height
        )

        total_captures = sum(self._capture_counts.values())
        if total_captures > 0:
            adjacent_pct = 100.0 * self._capture_counts[ADJACENT] / total_captures
            directed_pct = 100.0 * self._capture_counts[DIRECTED] / total_captures
            undirected_pct = 100.0 * self._capture_counts[UNDIRECTED] / total_captures
        else:
            adjacent_pct = directed_pct = undirected_pct = 0.0

        apples_eaten_per_tick = (
            self._apples_eaten_interval / self._config.logging.log_interval_ticks
        )

        self._prune_birth_events(cfg.ne_window_ticks)
        births_by_parent = Counter(parent for _, parent in self._birth_events)
        offspring_counts = [births_by_parent.get(a, 0) for a in pop]
        n_e = effective_population_size(offspring_counts)

        row = (
            f"{_mean(steer_scores):.6f}",
            f"{forager_pct:.6f}",
            f"{_mean(hidden_counts):.6f}",
            f"{_mean(novelty_scores):.6f}",
            f"{agent_density_global:.10f}",
            f"{apple_density_global:.10f}",
            f"{_mean([float(x) for x in self._local_agent_density_samples]):.6f}",
            f"{_mean([float(x) for x in self._local_apple_density_samples]):.6f}",
            f"{adjacent_pct:.6f}",
            f"{directed_pct:.6f}",
            f"{undirected_pct:.6f}",
            f"{apples_eaten_per_tick:.6f}",
            f"{n_e:.6f}",
        )

        self._capture_counts = {ADJACENT: 0, DIRECTED: 0, UNDIRECTED: 0}
        self._local_agent_density_samples = []
        self._local_apple_density_samples = []
        self._apples_eaten_interval = 0
        return row

    def _prune_birth_events(self, window_ticks: int) -> None:
        """Drop birth events older than the N_e rolling window."""
        cutoff = self.tick_count - window_ticks
        while self._birth_events and self._birth_events[0][0] < cutoff:
            self._birth_events.popleft()

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

    def _forage_rates(self) -> list[float]:
        """Per-living-agent apples eaten per tick of life (a current-fitness proxy).

        Unlike ``record_apples`` (a lifetime high-water mark that only ratchets
        up), foraging rate reflects the *current* population's competence and is
        age-normalised, so a rising mean is direct evidence that selection is
        improving the controllers.
        """
        return [
            self._apples_eaten[agent] / max(agent.age, 1) for agent in self.population
        ]


def _mean(values: list[float]) -> float:
    """Arithmetic mean, or 0.0 for an empty list."""
    return sum(values) / len(values) if values else 0.0
