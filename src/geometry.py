"""Pure geometry helpers shared across perception, rendering, and HyperNEAT.

Split out of ``agent.py`` so ``src/hyperneat.py`` can reuse the exact same
egocentric ray-angle formula for substrate coordinates without an import
cycle (``agent.py`` builds networks via ``hyperneat.py`` when HyperNEAT is
enabled; ``hyperneat.py`` needs ray geometry — this module depends on
neither).
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
