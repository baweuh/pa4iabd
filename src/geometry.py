"""Pure geometry helpers shared across perception and rendering.

Split out of ``agent.py`` so other modules can reuse the exact same
egocentric ray-angle formula without importing ``agent.py`` itself.
"""

from __future__ import annotations

import math


def ray_angles(num_rays: int, fov_degrees: float, heading: float = 0.0) -> list[float]:
    """Egocentric ray angles (radians) centred on ``heading``.

    Ray 0 is the forward direction (``heading``); subsequent rays are spaced
    evenly across the full ``fov_degrees``. With ``fov == 360`` the rays cover
    the full circle. Shared by perception (``agent.py``), the renderer, and
    HyperNEAT substrate coordinates so they always agree on ray geometry.
    """
    step = math.radians(fov_degrees) / num_rays
    return [heading + i * step for i in range(num_rays)]
