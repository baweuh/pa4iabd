"""Agent: a living creature that senses, decides, moves, eats, reproduces, dies.

The Agent is the bridge between perception (``NeuralNetwork``) and the world
(``Environment``). Each tick it casts 16 rays, feeds distances/types plus its
own energy into its cached network, moves, eats nearby apples, and pays its
metabolic cost.

Invariants honoured here:
- n°1 — zero hardcoding: every number comes from ``SimConfig``.
- n°2 — energy is apple-equivalent PER TICK (drain + wall penalty per tick).
- n°4 — the network's topological sort is computed ONCE, at agent creation, and
  cached for the agent's whole life (``NeuralNetwork`` built in ``__init__``).
- n°5 — output velocity is magnitude-clamped to ``max_speed`` via
  ``clamp_velocity`` (direction preserved).

Raycasts are cast in ABSOLUTE world directions (fov 360° split evenly across
``num_rays``); the agent has no heading. The wall penalty zone is sensed only
implicitly — the network perceives wall proximity through the raycasts, never as
a dedicated input.
"""

from __future__ import annotations

import math
from random import Random

from src.config import SimConfig
from src.environment import Environment
from src.genome import Genome
from src.network import NeuralNetwork, clamp_velocity

# Ray-hit type encoding for the NN input (CLAUDE.md "Inputs NN : 33").
_TYPE_NOTHING = 0.0
_TYPE_APPLE = 0.5
_TYPE_WALL = 1.0


class Agent:
    """One creature: perception + energy metabolism + life cycle."""

    def __init__(
        self,
        genome: Genome,
        position: tuple[float, float],
        config: SimConfig,
        environment: Environment,
        rng: Random,
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

    # ------------------------------------------------------------------ #
    # Perception
    # ------------------------------------------------------------------ #
    def sense(self) -> list[float]:
        """Return the 33 NN inputs: 16 distances, 16 types, 1 energy.

        Layout (CLAUDE.md): ``[0..15]`` normalised distances ``[0→1]`` (1.0 when
        nothing within ``max_distance``), ``[16..31]`` types (0.0 rien / 0.5
        pomme / 1.0 mur), ``[32]`` normalised energy ``[0→1]``.
        """
        num_rays = self._config.sensors.num_rays
        max_dist = self._config.sensors.max_distance

        distances: list[float] = []
        types: list[float] = []
        for i in range(num_rays):
            angle = i * (2.0 * math.pi / num_rays)
            dx = math.cos(angle)
            dy = math.sin(angle)
            hit_dist, hit_type = self._cast_ray(dx, dy, max_dist)
            distances.append(hit_dist / max_dist)
            types.append(hit_type)

        energy_norm = max(0.0, min(1.0, self.energy / self._config.agent.max_energy))
        return distances + types + [energy_norm]

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
        """Run the cached network on the current senses; return clamped (vx, vy)."""
        raw_vx, raw_vy = self.network.activate(self.sense())
        return clamp_velocity(raw_vx, raw_vy, self._config.agent.max_speed)

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
