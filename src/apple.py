"""Apple data structure — a single food source in the world.

Energy and radius are world-level constants (AppleConfig); they are not stored
per-instance. Placement and relocation logic lives in Environment.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Apple:
    """Mutable position of one food source.

    ``respawn_timer`` counts down the ticks an eaten apple spends off-board
    before it reappears (managed by Environment); 0 means the apple is live.
    ``spawn_tick`` is the tick this apple last appeared (0 for the initial
    board) — diagnostics-only (capture classification's reference point,
    see ``src.diagnostics``), never read by simulation logic.
    """

    x: float
    y: float
    respawn_timer: int = 0
    spawn_tick: int = 0
