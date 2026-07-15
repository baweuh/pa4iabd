"""World geometry: wall penalty field and apple placement (CLAUDE.md invariants 1 & 6).

Responsibilities:
- Maintain the list of live apples, all guaranteed to spawn with their full body
  inside the safe zone (dist_to_wall >= penalty_zone.width + apple.radius).
- Expose the gradient wall-penalty formula for use by agents (Phase 5).
- Handle deferred respawn: an eaten apple leaves the live list for
  ``apple.respawn_delay`` ticks (CDC §5.2), then reappears at a fresh safe
  position. Energy stays apple-equivalent per tick (invariant n°2).
- No eating, no agent state, no rendering.
"""

from __future__ import annotations

from random import Random

import numpy as np

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
        # Apples eaten this period, counting down to their respawn.
        self._pending: list[Apple] = []
        # Cached (x, y) NumPy arrays of ``apples``, used by Agent's vectorised
        # raycast (perf-critical: called once per living agent per tick).
        # Invalidated (set to None) whenever ``apples`` changes membership or an
        # apple's position moves (mark_eaten / tick_respawns), then rebuilt lazily
        # on the next access — apples change at most a couple of times per tick
        # (~1 eaten, ~1 respawned) versus hundreds of agents reading them.
        self._apple_coords_cache: tuple[np.ndarray, np.ndarray] | None = None

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

    def live_apple_coords(self) -> tuple[np.ndarray, np.ndarray]:
        """Cached ``(x, y)`` NumPy arrays of every live apple, one entry each.

        Rebuilt lazily the first time it's read after ``apples`` changes; reused
        as-is by every agent that senses in between (see cache comment above).
        """
        if self._apple_coords_cache is None:
            xs = np.fromiter(
                (a.x for a in self.apples), dtype=np.float64, count=len(self.apples)
            )
            ys = np.fromiter(
                (a.y for a in self.apples), dtype=np.float64, count=len(self.apples)
            )
            self._apple_coords_cache = (xs, ys)
        return self._apple_coords_cache

    def mark_eaten(self, apple: Apple) -> None:
        """Remove a just-eaten apple from play; it will respawn after the delay.

        The apple leaves ``apples`` for ``_pending`` and starts its countdown.
        Its position is left untouched until ``tick_respawns`` relocates it.
        """
        self.apples.remove(apple)
        apple.respawn_timer = self._apple_cfg.respawn_delay
        self._pending.append(apple)
        self._apple_coords_cache = None

    def tick_respawns(self, rng: Random, tick: int = 0) -> None:
        """Advance every pending apple's countdown; respawn the ones that are due.

        Decrement each pending timer; when it reaches 0 the apple is relocated to
        a fresh safe position and returned to ``apples``. Called once per tick
        (Phase 6, step 8). Logs nothing — rendering is Phase 7. ``tick`` stamps
        the respawned apple's ``spawn_tick`` (diagnostics-only, see
        ``src.diagnostics``); the default 0 keeps every call site that doesn't
        care about it (most tests) unchanged.
        """
        still_pending: list[Apple] = []
        for apple in self._pending:
            apple.respawn_timer -= 1
            if apple.respawn_timer <= 0:
                apple.respawn_timer = 0
                apple.x, apple.y = self._random_safe_position(rng)
                apple.spawn_tick = tick
                self.apples.append(apple)
                self._apple_coords_cache = None
            else:
                still_pending.append(apple)
        self._pending = still_pending

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _random_safe_position(self, rng: Random) -> tuple[float, float]:
        """Uniform draw inside the radius-inset safe rectangle (invariant n°6)."""
        return (
            rng.uniform(self._x_min, self._x_max),
            rng.uniform(self._y_min, self._y_max),
        )
