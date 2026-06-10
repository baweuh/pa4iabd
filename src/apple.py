"""Apple data structure — a single food source in the world.

Energy and radius are world-level constants (AppleConfig); they are not stored
per-instance. Placement and relocation logic lives in Environment.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Apple:
    """Mutable position of one food source."""

    x: float
    y: float
