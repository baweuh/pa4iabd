"""World geometry: wall penalty field and apple placement (CLAUDE.md invariants 1 & 6).

Responsibilities:
- Maintain the list of live apples, all guaranteed to spawn with their full body
  inside the safe zone (dist_to_wall >= penalty_zone.width + apple.radius).
- Expose the gradient wall-penalty formula for use by agents (Phase 5).
- No eating, no agent state, no rendering.
"""

from __future__ import annotations

from random import Random

from src.apple import Apple
from src.config import AppleConfig, PenaltyZoneConfig, SimConfig, WorldConfig


class Environment:
    """World model: geometry, penalty field, and apple population."""

    def __init__(self, config: SimConfig, rng: Random) -> None:
        self._world: WorldConfig = config.world
        self._pz: PenaltyZoneConfig = config.penalty_zone
        self._apple_cfg: AppleConfig = config.apple

        zw = self._pz.width
        r = self._apple_cfg.radius
        self._x_min = zw + r
        self._x_max = self._world.width - zw - r
        self._y_min = zw + r
        self._y_max = self._world.height - zw - r

        if self._x_max <= self._x_min or self._y_max <= self._y_min:
            raise ValueError(
                "penalty_zone.width + apple.radius leaves no safe spawn region; "
                "reduce penalty_zone.width or apple.radius"
            )

        self.apples: list[Apple] = [
            Apple(*self._random_safe_position(rng))
            for _ in range(self._apple_cfg.count)
        ]

    # ------------------------------------------------------------------ #
    # Public geometry helpers
    # ------------------------------------------------------------------ #

    def dist_to_wall(self, x: float, y: float) -> float:
        """Minimum distance from (x, y) to any wall."""
        return min(x, self._world.width - x, y, self._world.height - y)

    def penalty_at(self, x: float, y: float) -> float:
        """Energy drained per tick at (x, y) — gradient, not binary (invariant n°2).

        penalty = max_drain * (1 - dist / zone_width)  if dist < zone_width
                = 0.0                                   otherwise
        """
        dist = self.dist_to_wall(x, y)
        if dist < self._pz.width:
            return self._pz.max_drain * (1.0 - dist / self._pz.width)
        return 0.0

    def in_safe_zone(self, x: float, y: float) -> bool:
        """True when (x, y) is outside the penalty zone (agent-facing helper)."""
        return self.dist_to_wall(x, y) >= self._pz.width

    def respawn(self, apple: Apple, rng: Random) -> None:
        """Relocate *apple* to a fresh safe position distinct from its current one."""
        old_x, old_y = apple.x, apple.y
        new_x, new_y = self._random_safe_position(rng)
        while new_x == old_x and new_y == old_y:
            new_x, new_y = self._random_safe_position(rng)
        apple.x = new_x
        apple.y = new_y

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _random_safe_position(self, rng: Random) -> tuple[float, float]:
        """Uniform draw inside the radius-inset safe rectangle (invariant n°6)."""
        return (
            rng.uniform(self._x_min, self._x_max),
            rng.uniform(self._y_min, self._y_max),
        )
