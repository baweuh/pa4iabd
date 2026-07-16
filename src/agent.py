"""Agent: a living creature that senses, decides, moves, eats, reproduces, dies.

The Agent is the bridge between perception (``NeuralNetwork``) and the world
(``Environment``). Each tick it casts 16 rays, feeds distances/apple-flags/
wall-flags plus its own energy into its cached network, updates its heading,
moves, eats nearby apples, and pays its metabolic cost.

Invariants honoured here:
- n°1 — zero hardcoding: every number comes from ``SimConfig``.
- n°2 — energy is apple-equivalent PER TICK (drain + wall penalty per tick).
- n°4 — the network's fixed-topology matrices are built ONCE, at agent
  creation, and cached for the agent's whole life (``NeuralNetwork`` built
  in ``__init__``, poc3).
- n°5 — egocentric outputs: output[0] × max_speed = signed forward speed;
  output[1] × max_turn_rate = heading delta (rad/tick).

Raycasts are cast in EGOCENTRIC directions centred on the agent's heading (ray 0
= forward). The wall penalty zone is sensed only implicitly — the network
perceives wall proximity through the raycasts, never as a dedicated input.
"""

from __future__ import annotations

import math
from random import Random

import numpy as np

from src.apple import Apple
from src.config import SimConfig
from src.diagnostics import steer_score as _compute_steer_score
from src.environment import Environment
from src.genome import Genome
from src.geometry import ray_angles
from src.network import NeuralNetwork
from src.novelty import behavior_descriptor as _compute_descriptor


class Agent:
    """One creature: perception + energy metabolism + life cycle."""

    def __init__(
        self,
        genome: Genome,
        position: tuple[float, float],
        config: SimConfig,
        environment: Environment,
        rng: Random,
        generation: int = 0,
        heading: float | None = None,
    ) -> None:
        self.genome = genome
        self.x, self.y = position
        self._config = config
        self._env = environment
        self._rng = rng

        # Invariant n°4: build the network ONCE, here — a fixed-topology
        # matrix stack (src.genome.network_layer_shapes), never rebuilt or
        # re-derived for the agent's whole life.
        self.network = NeuralNetwork(genome, config.network)

        self.energy: float = config.agent.initial_energy
        self.age: int = 0
        self.alive: bool = True
        # Generations since a founder (founder == 0). Tracks evolutionary depth so
        # adaptation across lineages is measurable; set by reproduce().
        self.generation: int = generation
        # Facing direction in radians. None → random; passed explicitly in tests and
        # reproduce() (child inherits parent direction).
        self.heading: float = (
            heading if heading is not None else rng.uniform(0.0, 2.0 * math.pi)
        )
        # Senses used for the most recent decision (None before the first
        # activate()). Read by the renderer so drawn rays are exactly the rays
        # the agent acted on — and perception is never recomputed for display.
        self.last_senses: list[float] | None = None
        # Magnitude of the forward speed chosen on the last activate(); charged as
        # activity metabolism in metabolize() (per tick — invariant n°2).
        self._last_speed: float = 0.0
        # Proprioception: actual normalised displacement from the previous tick.
        # 0.0 = fully blocked by a wall; 1.0 = moved at full max_speed.
        self._last_actual_speed: float = 0.0
        # Lifetime apples eaten — updated by Simulation each tick, read by the renderer
        # to identify the best forager (forage_rate = apples_eaten / max(age, 1)).
        self.apples_eaten: int = 0
        # Lifetime capture classification (diagnostics only, src.diagnostics),
        # updated by Simulation alongside apples_eaten: "directed" = genuine
        # steering toward the apple; "fortuitous" folds together "adjacent"
        # (free catch, no travel needed) and "undirected" (random-walk luck) —
        # the population-level CSV keeps the finer 3-way split.
        self.directed_captures: int = 0
        self.fortuitous_captures: int = 0
        # Behavioural-novelty descriptor (turn-response profile). Deterministic
        # from the network → computed once, lazily, and cached for life.
        self._behavior_descriptor: list[float] | None = None
        # Steering-response correlation (r apple-on-left ↔ turns-left).
        # Deterministic from the frozen network → cached for life, like the
        # descriptor above. The diagnostics CSV reads it over the whole
        # population every log interval; recomputing num_rays activations per
        # agent each time was a measurable per-log-tick hitch.
        self._steer_score: float | None = None
        # Raw novelty score (mean distance to nearest behaviours), refreshed by
        # Simulation every novelty.recompute_interval ticks; 0.0 until first
        # refresh. Population-derived, not intrinsic — hence a plain slot.
        self.novelty_score: float = 0.0

    # ------------------------------------------------------------------ #
    # Perception
    # ------------------------------------------------------------------ #
    def sense(self) -> list[float]:
        """Return ``config.network.num_inputs`` NN inputs, per the sensor layout.

        Canonical 67-input layout (all toggles on, ``split_distance``):
        ``[0..15]``   apple_dist  normalised per ray (1.0 = none in range)
        ``[16..31]``  wall_dist   normalised per ray
        ``[32..47]``  apple_flag  binary 0/1 per ray
        ``[48..63]``  wall_flag   binary 0/1 per ray
        ``[64]``      energy      normalised [0→1]
        ``[65]``      actual_speed proprioception from previous tick [0→1]  (opt)
        ``[66]``      apples_in_view fraction of rays that see an apple [0→1] (opt)

        With ``split_distance`` off the two distance blocks collapse into one
        combined nearest-object distance block (legacy 49-input layout); the two
        proprioceptive scalars are appended only when their toggle is on.
        """
        sensors = self._config.sensors
        max_dist = sensors.max_distance
        angles = np.array(
            ray_angles(sensors.num_rays, sensors.fov, self.heading), dtype=np.float64
        )
        apple_dist, wall_dist = self._cast_rays(angles, max_dist)

        apple_dists = (apple_dist / max_dist).tolist()
        wall_dists = (wall_dist / max_dist).tolist()
        apple_flags = (apple_dist < max_dist).astype(np.float64).tolist()
        wall_flags = (wall_dist < max_dist).astype(np.float64).tolist()

        energy_norm = max(0.0, min(1.0, self.energy / self._config.agent.max_energy))
        if sensors.split_distance:
            inputs = apple_dists + wall_dists + apple_flags + wall_flags
        else:
            combined_dists = (np.minimum(apple_dist, wall_dist) / max_dist).tolist()
            inputs = combined_dists + apple_flags + wall_flags
        inputs = inputs + [energy_norm]
        if sensors.proprioception:
            inputs.append(self._last_actual_speed)
        if sensors.apples_in_view:
            inputs.append(sum(apple_flags) / len(apple_flags))
        return inputs

    def _cast_rays(
        self, angles: "np.ndarray", max_dist: float
    ) -> tuple["np.ndarray", "np.ndarray"]:
        """Independent nearest-apple and nearest-wall distances for ALL rays at once.

        Returns ``(apple_dists, wall_dists)`` arrays (one entry per ray), each
        clamped to ``max_dist`` when no hit of that type lies within range — same
        semantics as casting each ray one at a time, but batched with NumPy: the
        raycast is the perf-critical path (O(rays×live apples) per agent per
        tick), so this replaces the nested Python loop with vectorised array ops.
        """
        dx = np.cos(angles)
        dy = np.sin(angles)
        wall_dist = _ray_walls_vec(
            self.x, self.y, dx, dy, self._config.world.width, self._config.world.height
        )
        wall_dist = np.minimum(wall_dist, max_dist)

        cx, cy = self._env.live_apple_coords()
        if cx.size:
            apple_dist = _ray_circles_vec(
                self.x, self.y, dx, dy, cx, cy, self._config.apple.radius
            )
            apple_dist = np.minimum(apple_dist, max_dist)
        else:
            apple_dist = np.full(angles.shape, max_dist)

        return apple_dist, wall_dist

    # ------------------------------------------------------------------ #
    # Decision and movement
    # ------------------------------------------------------------------ #
    def activate(self) -> tuple[float, float]:
        """Sense, run the cached network, and return world-frame (vx, vy).

        Convenience wrapper around ``decide(self.sense())`` — kept so single-agent
        callers (tests, tools) need not know about the batched perception path.
        The batched tick in ``simulation.py`` computes every agent's senses in one
        NumPy pass (see ``batch_sense``) and calls ``decide`` directly.
        """
        return self.decide(self.sense())

    def decide(self, senses: list[float]) -> tuple[float, float]:
        """Run the cached network on ``senses``; update heading, return (vx, vy).

        output[0] (tanh ∈ (-1,1)) × max_speed  = signed forward/backward speed.
        output[1] (tanh ∈ (-1,1)) × max_turn_rate = heading delta (rad/tick).

        Stores ``senses`` in ``last_senses`` (read by the renderer, invariant n°7)
        so displayed rays are exactly the rays the agent acted on.
        """
        self.last_senses = senses
        raw = self.network.activate(senses)
        return self._act_on_raw(raw)

    def decide_from_raw(
        self, senses: list[float], raw: tuple[float, float]
    ) -> tuple[float, float]:
        """Like :meth:`decide`, but ``raw`` was already computed elsewhere.

        Used by the batched tick path (``src.network.batch_activate`` runs
        the whole population's forward pass in one NumPy call — see
        ``Simulation.tick``) so the per-agent egocentric transform below
        doesn't re-run the network a second time. Behaviourally identical to
        ``decide(senses)``.
        """
        self.last_senses = senses
        return self._act_on_raw(raw)

    def _act_on_raw(self, raw) -> tuple[float, float]:
        """Egocentric transform shared by :meth:`decide`/:meth:`decide_from_raw`.

        output[0] (tanh ∈ (-1,1)) × max_speed  = signed forward/backward speed.
        output[1] (tanh ∈ (-1,1)) × max_turn_rate = heading delta (rad/tick).
        """
        # Output layer is linear; apply tanh explicitly to bound speed and turn.
        speed = math.tanh(raw[0]) * self._config.agent.max_speed
        self._last_speed = abs(speed)
        self.heading = (
            self.heading + math.tanh(raw[1]) * self._config.agent.max_turn_rate
        ) % (2.0 * math.pi)
        return speed * math.cos(self.heading), speed * math.sin(self.heading)

    def move(self, vx: float, vy: float) -> None:
        """Translate by (vx, vy), clamped inside the walled world.

        Stores the normalised actual displacement for proprioceptive sensing
        (input [65]): 0.0 = fully blocked by a wall; 1.0 = moved at max_speed.
        """
        radius = self._config.agent.radius
        new_x = _clamp(self.x + vx, radius, self._config.world.width - radius)
        new_y = _clamp(self.y + vy, radius, self._config.world.height - radius)
        self._last_actual_speed = (
            math.hypot(new_x - self.x, new_y - self.y) / self._config.agent.max_speed
        )
        self.x = new_x
        self.y = new_y

    @property
    def last_actual_speed(self) -> float:
        """Normalised actual displacement from the previous tick (proprioception).

        Public read accessor so ``batch_sense`` can gather it across the whole
        population without reaching into a protected attribute.
        """
        return self._last_actual_speed

    @property
    def behavior_descriptor(self) -> list[float]:
        """Cached turn-response profile (novelty descriptor); computed once.

        Deterministic from the (frozen) network, so it is safe to memoise for the
        agent's whole life — mirrors how the network's topo-sort is cached once.
        """
        if self._behavior_descriptor is None:
            self._behavior_descriptor = _compute_descriptor(
                self.network, self._config.sensors
            )
        return self._behavior_descriptor

    @property
    def steer_score(self) -> float:
        """Cached steering-response correlation; computed once (see __init__).

        Deterministic from the (frozen) network, memoised for life like
        :attr:`behavior_descriptor`. Equal to
        ``src.diagnostics.steer_score(self.network, config.sensors)``.
        """
        if self._steer_score is None:
            self._steer_score = _compute_steer_score(self.network, self._config.sensors)
        return self._steer_score

    # ------------------------------------------------------------------ #
    # Energy (per TICK — invariant n°2)
    # ------------------------------------------------------------------ #
    def metabolize(self) -> None:
        """Pay base drain, the gradient wall penalty, and activity cost this tick.

        Activity cost (``move_cost × |forward speed|``) makes aimless wandering
        expensive so directed, food-efficient foraging is selected for. With
        ``move_cost == 0.0`` movement is free (legacy behaviour).
        """
        self.energy -= self._config.agent.energy_drain_per_tick
        self.energy -= self._config.agent.move_cost * self._last_speed
        self.energy -= self._env.penalty_at(self.x, self.y)
        self.energy = min(self.energy, self._config.agent.max_energy)

    def eat(self) -> list[Apple]:
        """Consume every apple whose body overlaps the agent; defer their respawn.

        Returns the apples eaten this tick (``len(...)`` for a plain count;
        Simulation also uses the apples themselves to classify captures, see
        ``src.diagnostics``). Energy is capped at ``max_energy``. Eaten apples
        are handed to ``Environment.mark_eaten`` so they reappear after
        ``apple.respawn_delay`` ticks (CDC §5.2); they are collected first to
        avoid mutating ``env.apples`` while iterating it.
        """
        reach = self._config.agent.radius + self._config.apple.radius
        gain = self._config.apple.energy
        bitten = [
            apple
            for apple in self._env.apples
            if math.hypot(apple.x - self.x, apple.y - self.y) <= reach
        ]
        for apple in bitten:
            self.energy = min(self.energy + gain, self._config.agent.max_energy)
            self._env.mark_eaten(apple)
        return bitten

    # ------------------------------------------------------------------ #
    # Life cycle
    # ------------------------------------------------------------------ #
    def is_dead(self) -> bool:
        """Dead by famine (energy depleted) or old age (max_age reached)."""
        return self.energy <= 0.0 or self.age >= self._config.agent.max_age

    def can_reproduce(self) -> bool:
        """True once energy reaches the reproduction threshold."""
        return self.energy >= self._config.agent.reproduction_threshold

    def reproduce(self, mate: "Agent | None" = None) -> "Agent":
        """Spawn a mutated child near the parent; the parent pays the cost.

        With ``mate`` the child genome comes from NEAT crossover (``self`` treated
        as the fitter parent, since it is the one filling the reproduction slot);
        without a mate it is a clone of ``self`` (legacy asexual path). Either way
        the child genome is then mutated. The child is a fresh ``Agent`` (so it
        builds its own cached network) starting with ``initial_energy`` and placed
        within ``±radius`` of the parent, clamped inside the world.
        """
        self.energy -= self._config.agent.reproduction_cost

        if mate is None:
            child_genome = self.genome.clone()
        else:
            child_genome = Genome.crossover(self.genome, mate.genome, self._rng)
        child_genome.mutate(self._config.genome, self._rng)

        radius = self._config.agent.radius
        child_x = _clamp(
            self.x + self._rng.uniform(-radius, radius),
            radius,
            self._config.world.width - radius,
        )
        child_y = _clamp(
            self.y + self._rng.uniform(-radius, radius),
            radius,
            self._config.world.height - radius,
        )
        return Agent(
            child_genome,
            (child_x, child_y),
            self._config,
            self._env,
            self._rng,
            generation=self.generation + 1,
            heading=self.heading,
        )


# ---------------------------------------------------------------------- #
# Geometry helpers (pure functions)
# ---------------------------------------------------------------------- #
def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _ray_walls_vec(
    px: float,
    py: float,
    dx: "np.ndarray",
    dy: "np.ndarray",
    width: float,
    height: float,
) -> "np.ndarray":
    """Smallest positive distance from (px, py) along each (dx, dy) to a box wall.

    Vectorised over rays (one ``dx``/``dy`` pair per ray). The ray directions
    are unit vectors, so the parameter ``t`` equals distance. A ray exactly
    parallel to an axis (``dx`` or ``dy`` == 0) contributes no candidate on
    that axis, same as the scalar version this replaces.
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        tx = np.where(
            dx > 0, (width - px) / dx, np.where(dx < 0, (0.0 - px) / dx, np.inf)
        )
        ty = np.where(
            dy > 0, (height - py) / dy, np.where(dy < 0, (0.0 - py) / dy, np.inf)
        )
    tx = np.where(tx > 0.0, tx, np.inf)
    ty = np.where(ty > 0.0, ty, np.inf)
    return np.minimum(tx, ty)


def _ray_circles_vec(
    px: float,
    py: float,
    dx: "np.ndarray",
    dy: "np.ndarray",
    cx: "np.ndarray",
    cy: "np.ndarray",
    radius: float,
) -> "np.ndarray":
    """Nearest positive distance from (px, py) along each unit (dx, dy) to the
    nearest of the circles centred at (cx, cy) — one distance per ray.

    Vectorised over the full (rays × circles) grid at once. ``inf`` where a
    ray misses every circle or only meets them behind the origin. Solves
    ``|P + t·D − C|² = r²`` with ``|D| = 1`` (a == 1), same formula as the
    scalar version this replaces.
    """
    fx = px - cx[np.newaxis, :]  # (1, A)
    fy = py - cy[np.newaxis, :]
    b = 2.0 * (fx * dx[:, np.newaxis] + fy * dy[:, np.newaxis])  # (R, A)
    disc = b * b - 4.0 * (fx * fx + fy * fy - radius * radius)  # (1, A) -> (R, A)
    sqrt_disc = np.sqrt(np.where(disc >= 0.0, disc, 0.0))
    near, far = (-b - sqrt_disc) / 2.0, (-b + sqrt_disc) / 2.0
    hit = np.where(
        (disc >= 0.0) & (near > 0.0),
        near,
        np.where((disc >= 0.0) & (far > 0.0), far, np.inf),
    )
    return np.min(hit, axis=1)  # (R,) nearest circle per ray


def batch_sense(
    agents: "list[Agent]", env: Environment, config: SimConfig
) -> list[list[float]]:
    """Perceive the WHOLE population in one NumPy pass — one row per agent.

    Bit-identical to calling ``Agent.sense()`` on each agent against the same
    frozen world (proven by ``tests/test_batch_sense.py``), but casts every
    agent's rays in a single ``(P × rays × apples)`` broadcast instead of P
    Python-level calls. Perception is 57% of the tick and its dominant cost
    (poc2.4 perf chantier): this is the batched replacement.

    The world is read ONCE here (positions, headings, live apples at tick start),
    so every agent perceives the same tick-start snapshot — see the tick's
    "freeze then perceive" contract in ``simulation.py``. Agents never sense one
    another (only apples and walls), so batching changes nothing except that an
    agent may now perceive an apple a lower-index agent eats the same tick.
    """
    sensors = config.sensors
    max_dist = sensors.max_distance
    num_rays = sensors.num_rays
    count = len(agents)
    if count == 0:
        return []

    px = np.fromiter((a.x for a in agents), np.float64, count)
    py = np.fromiter((a.y for a in agents), np.float64, count)
    heading = np.fromiter((a.heading for a in agents), np.float64, count)

    step = math.radians(sensors.fov) / num_rays
    ray_offsets = step * np.arange(num_rays)  # (R,) — same as ray_angles()
    angles = heading[:, np.newaxis] + ray_offsets[np.newaxis, :]  # (P, R)
    dx = np.cos(angles)
    dy = np.sin(angles)

    # --- walls: vectorised over (P, R), same formula as _ray_walls_vec ---
    width, height = config.world.width, config.world.height
    with np.errstate(divide="ignore", invalid="ignore"):
        tx = np.where(
            dx > 0,
            (width - px[:, np.newaxis]) / dx,
            np.where(dx < 0, (0.0 - px[:, np.newaxis]) / dx, np.inf),
        )
        ty = np.where(
            dy > 0,
            (height - py[:, np.newaxis]) / dy,
            np.where(dy < 0, (0.0 - py[:, np.newaxis]) / dy, np.inf),
        )
    tx = np.where(tx > 0.0, tx, np.inf)
    ty = np.where(ty > 0.0, ty, np.inf)
    wall_dist = np.minimum(np.minimum(tx, ty), max_dist)  # (P, R)

    # --- apples: vectorised over (P, R, A), same formula as _ray_circles_vec ---
    cx, cy = env.live_apple_coords()
    if cx.size:
        radius = config.apple.radius
        fx = px[:, np.newaxis, np.newaxis] - cx[np.newaxis, np.newaxis, :]  # (P,1,A)
        fy = py[:, np.newaxis, np.newaxis] - cy[np.newaxis, np.newaxis, :]
        b = 2.0 * (fx * dx[:, :, np.newaxis] + fy * dy[:, :, np.newaxis])  # (P,R,A)
        disc = b * b - 4.0 * (fx * fx + fy * fy - radius * radius)
        sqrt_disc = np.sqrt(np.where(disc >= 0.0, disc, 0.0))
        near, far = (-b - sqrt_disc) / 2.0, (-b + sqrt_disc) / 2.0
        hit = np.where(
            (disc >= 0.0) & (near > 0.0),
            near,
            np.where((disc >= 0.0) & (far > 0.0), far, np.inf),
        )
        apple_dist = np.minimum(np.min(hit, axis=2), max_dist)  # (P, R)
    else:
        apple_dist = np.full((count, num_rays), max_dist)

    # --- assemble the configured layout, column order matching sense() ---
    apple_flag = (apple_dist < max_dist).astype(np.float64)
    wall_flag = (wall_dist < max_dist).astype(np.float64)
    max_energy = config.agent.max_energy
    energy = np.clip(
        np.fromiter((a.energy for a in agents), np.float64, count) / max_energy,
        0.0,
        1.0,
    )[:, np.newaxis]

    if sensors.split_distance:
        blocks = [apple_dist / max_dist, wall_dist / max_dist, apple_flag, wall_flag]
    else:
        combined = np.minimum(apple_dist, wall_dist) / max_dist
        blocks = [combined, apple_flag, wall_flag]
    blocks.append(energy)
    if sensors.proprioception:
        blocks.append(
            np.fromiter((a.last_actual_speed for a in agents), np.float64, count)[
                :, np.newaxis
            ]
        )
    if sensors.apples_in_view:
        blocks.append(apple_flag.mean(axis=1, keepdims=True))

    return np.concatenate(blocks, axis=1).tolist()
