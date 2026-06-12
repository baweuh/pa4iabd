"""Agent: a living creature that senses, decides, moves, eats, reproduces, dies.

The Agent is the bridge between perception (``NeuralNetwork``) and the world
(``Environment``). Each tick it casts 16 rays, feeds distances/apple-flags/
wall-flags plus its own energy into its cached network, updates its heading,
moves, eats nearby apples, and pays its metabolic cost.

Invariants honoured here:
- n°1 — zero hardcoding: every number comes from ``SimConfig``.
- n°2 — energy is apple-equivalent PER TICK (drain + wall penalty per tick).
- n°4 — the network's topological sort is computed ONCE, at agent creation, and
  cached for the agent's whole life (``NeuralNetwork`` built in ``__init__``).
- n°5 — egocentric outputs: output[0] × max_speed = signed forward speed;
  output[1] × max_turn_rate = heading delta (rad/tick).

Raycasts are cast in EGOCENTRIC directions centred on the agent's heading (ray 0
= forward). The wall penalty zone is sensed only implicitly — the network
perceives wall proximity through the raycasts, never as a dedicated input.
"""

from __future__ import annotations

import math
from random import Random

from src.config import SimConfig
from src.environment import Environment
from src.genome import Genome
from src.network import NeuralNetwork

# Internal hit-type tokens used by _cast_ray (not exposed as NN inputs directly).
_TYPE_NOTHING = 0.0
_TYPE_APPLE = 0.5
_TYPE_WALL = 1.0


def ray_angles(num_rays: int, fov_degrees: float, heading: float = 0.0) -> list[float]:
    """Egocentric ray angles (radians) centred on ``heading``.

    Ray 0 is the forward direction (``heading``); subsequent rays are spaced
    evenly across the full ``fov_degrees``. With ``fov == 360`` the rays cover
    the full circle. Shared with the renderer so displayed rays always match
    perceived rays.
    """
    step = math.radians(fov_degrees) / num_rays
    return [heading + i * step for i in range(num_rays)]


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

        # Invariant n°4: build (and topo-sort) the network ONCE, here.
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

    # ------------------------------------------------------------------ #
    # Perception
    # ------------------------------------------------------------------ #
    def sense(self) -> list[float]:
        """Return 49 NN inputs: 16 distances, 16 apple flags, 16 wall flags, 1 energy.

        Layout (CLAUDE.md): ``[0..15]`` normalised distances ``[0→1]`` (rays
        centred on heading), ``[16..31]`` apple-presence flags (0.0/1.0),
        ``[32..47]`` wall-presence flags (0.0/1.0), ``[48]`` normalised energy.

        Splitting apple/wall into separate binary channels lets the network learn
        independent weights for each stimulus type, which is structurally easier
        than the single-scalar encoding (0.0/0.5/1.0) it replaces.
        """
        max_dist = self._config.sensors.max_distance
        distances: list[float] = []
        apple_flags: list[float] = []
        wall_flags: list[float] = []
        for angle in ray_angles(
            self._config.sensors.num_rays, self._config.sensors.fov, self.heading
        ):
            dx = math.cos(angle)
            dy = math.sin(angle)
            hit_dist, hit_type = self._cast_ray(dx, dy, max_dist)
            distances.append(hit_dist / max_dist)
            apple_flags.append(1.0 if hit_type == _TYPE_APPLE else 0.0)
            wall_flags.append(1.0 if hit_type == _TYPE_WALL else 0.0)

        energy_norm = max(0.0, min(1.0, self.energy / self._config.agent.max_energy))
        return distances + apple_flags + wall_flags + [energy_norm]

    def _cast_ray(self, dx: float, dy: float, max_dist: float) -> tuple[float, float]:
        """First-hit search along the unit ray (dx, dy) from the agent.

        Returns ``(distance, type)``. ``distance`` is clamped to ``max_dist`` and
        ``type`` is ``_TYPE_NOTHING`` when neither apple nor wall lies within
        range.
        """
        hit_dist = math.inf
        hit_type = _TYPE_NOTHING

        # Apples: nearest positive ray-circle intersection.
        apple_radius = self._config.apple.radius
        for apple in self._env.apples:
            t = _ray_circle(self.x, self.y, dx, dy, apple.x, apple.y, apple_radius)
            if t is not None and t < hit_dist:
                hit_dist = t
                hit_type = _TYPE_APPLE

        # Walls: nearest positive ray-box intersection (always finite indoors).
        wall_t = _ray_walls(
            self.x,
            self.y,
            dx,
            dy,
            self._config.world.width,
            self._config.world.height,
        )
        if wall_t is not None and wall_t < hit_dist:
            hit_dist = wall_t
            hit_type = _TYPE_WALL

        if hit_dist >= max_dist:
            return max_dist, _TYPE_NOTHING
        return hit_dist, hit_type

    # ------------------------------------------------------------------ #
    # Decision and movement
    # ------------------------------------------------------------------ #
    def activate(self) -> tuple[float, float]:
        """Run the cached network; update heading and return world-frame (vx, vy).

        output[0] (tanh ∈ (-1,1)) × max_speed  = signed forward/backward speed.
        output[1] (tanh ∈ (-1,1)) × max_turn_rate = heading delta (rad/tick).
        """
        self.last_senses = self.sense()
        raw = self.network.activate(self.last_senses)
        # Output nodes are linear; apply tanh explicitly to bound speed and turn.
        speed = math.tanh(raw[0]) * self._config.agent.max_speed
        self.heading = (
            self.heading + math.tanh(raw[1]) * self._config.agent.max_turn_rate
        ) % (2.0 * math.pi)
        return speed * math.cos(self.heading), speed * math.sin(self.heading)

    def move(self, vx: float, vy: float) -> None:
        """Translate by (vx, vy), staying inside the walled world (body-clamped)."""
        radius = self._config.agent.radius
        self.x = _clamp(self.x + vx, radius, self._config.world.width - radius)
        self.y = _clamp(self.y + vy, radius, self._config.world.height - radius)

    # ------------------------------------------------------------------ #
    # Energy (per TICK — invariant n°2)
    # ------------------------------------------------------------------ #
    def metabolize(self) -> None:
        """Pay the base drain and the gradient wall penalty for this tick."""
        self.energy -= self._config.agent.energy_drain_per_tick
        self.energy -= self._env.penalty_at(self.x, self.y)
        self.energy = min(self.energy, self._config.agent.max_energy)

    def eat(self) -> int:
        """Consume every apple whose body overlaps the agent; defer their respawn.

        Returns the number of apples eaten this tick. Energy is capped at
        ``max_energy``. Eaten apples are handed to ``Environment.mark_eaten`` so
        they reappear after ``apple.respawn_delay`` ticks (CDC §5.2); they are
        collected first to avoid mutating ``env.apples`` while iterating it.
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
        return len(bitten)

    # ------------------------------------------------------------------ #
    # Life cycle
    # ------------------------------------------------------------------ #
    def is_dead(self) -> bool:
        """Dead by famine (energy depleted) or old age (max_age reached)."""
        return self.energy <= 0.0 or self.age >= self._config.agent.max_age

    def can_reproduce(self) -> bool:
        """True once energy reaches the reproduction threshold."""
        return self.energy >= self._config.agent.reproduction_threshold

    def reproduce(self) -> "Agent":
        """Spawn a mutated child near the parent; the parent pays the cost.

        The child genome is a mutated clone; the child is a fresh ``Agent`` (so it
        builds its own cached network) starting with ``initial_energy`` and placed
        within ``±radius`` of the parent, clamped inside the world.
        """
        self.energy -= self._config.agent.reproduction_cost

        child_genome = self.genome.clone()
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

    def update(self) -> None:
        """Advance one tick: age, decide, move, eat, metabolize, check death.

        Convenience helper for callers that want default step ordering;
        reproduction is left to the orchestrator (Phase 6) since it yields a new
        agent that the population must collect.
        """
        self.age += 1
        vx, vy = self.activate()
        self.move(vx, vy)
        self.eat()
        self.metabolize()
        if self.is_dead():
            self.alive = False


# ---------------------------------------------------------------------- #
# Geometry helpers (pure functions)
# ---------------------------------------------------------------------- #
def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _ray_walls(
    px: float, py: float, dx: float, dy: float, width: float, height: float
) -> float | None:
    """Smallest positive distance from (px, py) along (dx, dy) to a box wall.

    The ray direction is a unit vector, so the parameter ``t`` equals distance.
    Returns ``None`` only for the degenerate zero-direction ray.
    """
    best: float | None = None
    if dx > 0:
        best = _closer(best, (width - px) / dx)
    elif dx < 0:
        best = _closer(best, (0.0 - px) / dx)
    if dy > 0:
        best = _closer(best, (height - py) / dy)
    elif dy < 0:
        best = _closer(best, (0.0 - py) / dy)
    return best


def _ray_circle(
    px: float,
    py: float,
    dx: float,
    dy: float,
    cx: float,
    cy: float,
    radius: float,
) -> float | None:
    """Nearest positive distance from (px, py) along unit (dx, dy) to a circle.

    Returns ``None`` when the ray misses the circle or only meets it behind the
    origin. Solves ``|P + t·D − C|² = r²`` with ``|D| = 1`` (a == 1).
    """
    fx = px - cx
    fy = py - cy
    b = 2.0 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - radius * radius
    disc = b * b - 4.0 * c
    if disc < 0.0:
        return None
    sqrt_disc = math.sqrt(disc)
    t_near = (-b - sqrt_disc) / 2.0
    if t_near > 0.0:
        return t_near
    t_far = (-b + sqrt_disc) / 2.0
    if t_far > 0.0:
        return t_far
    return None


def _closer(current: float | None, candidate: float) -> float | None:
    """Keep the smaller strictly-positive distance."""
    if candidate <= 0.0:
        return current
    if current is None or candidate < current:
        return candidate
    return current
