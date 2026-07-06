"""
src/environment.py — Pommes, zone pénalité, spawn/respawn, détection collision.
CDC §3 : Espace de simulation, zone de pénalité murale, pommes (ressource).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import numpy as np

from .config import EnvironmentConfig


@dataclass
class Apple:
    """Une pomme dans l'environnement."""
    x: float
    y: float
    respawn_at_tick: int = -1  # tick auquel la pomme réapparaît (-1 = active)


class Environment:
    """
    Gère l'espace de simulation 2D, les pommes, la zone de pénalité murale.
    CDC §3.1–3.3.
    """

    def __init__(self, cfg: EnvironmentConfig, rng: random.Random) -> None:
        self.cfg = cfg
        self.rng = rng
        self.width: float = float(cfg.env_width)
        self.height: float = float(cfg.env_height)
        self.zone_width: float = float(cfg.zone_width)
        self.zone_max_drain: float = float(cfg.zone_max_drain)

        # Zone safe (où les pommes peuvent spawn)
        self.safe_min: float = self.zone_width
        self.safe_max_x: float = self.width - self.zone_width
        self.safe_max_y: float = self.height - self.zone_width

        # Pommes
        self.apples: list[Apple] = []
        self._init_apples()

    def _init_apples(self) -> None:
        """Place food_count pommes dans la zone safe au démarrage."""
        for _ in range(self.cfg.food_count):
            x, y = self._random_safe_position()
            self.apples.append(Apple(x=x, y=y))

    def _random_safe_position(self) -> tuple[float, float]:
        """Position aléatoire dans la zone safe."""
        margin = 10  # petite marge interne
        x = self.rng.uniform(self.safe_min + margin, self.safe_max_x - margin)
        y = self.rng.uniform(self.safe_min + margin, self.safe_max_y - margin)
        return x, y

    def respawn_apples(self, current_tick: int) -> None:
        """Fait réapparaître les pommes dont le délai est écoulé (CDC §6.2 étape 8)."""
        for apple in self.apples:
            if apple.respawn_at_tick > 0 and current_tick >= apple.respawn_at_tick:
                apple.x, apple.y = self._random_safe_position()
                apple.respawn_at_tick = -1

    def eat_apple(self, apple_index: int, current_tick: int) -> None:
        """Supprime une pomme (contact agent) et programme son respawn."""
        apple = self.apples[apple_index]
        apple.respawn_at_tick = current_tick + self.cfg.food_respawn_delay

    @property
    def food_available(self) -> int:
        """Nombre de pommes actuellement actives."""
        return sum(1 for a in self.apples if a.respawn_at_tick < 0)

    def wall_penalty_drain(self, x: float, y: float) -> float:
        """
        Calcule le drain énergétique dû à la zone de pénalité murale.
        CDC §3.2 : gradient — plus l'agent est proche du mur, plus le drain est fort.
        Formule : penalty_drain = zone_max_drain × (1 − dist_mur / zone_width)
        """
        dist_to_nearest_wall = min(x, y, self.width - x, self.height - y)

        if dist_to_nearest_wall >= self.zone_width:
            return 0.0

        # Gradient linéaire
        ratio = dist_to_nearest_wall / self.zone_width
        return self.zone_max_drain * (1.0 - ratio)

    def is_in_wall(self, x: float, y: float, radius: float = 0.0) -> bool:
        """Vérifie si une position (avec rayon) est en dehors des murs."""
        return (
            x - radius < 0
            or x + radius > self.width
            or y - radius < 0
            or y + radius > self.height
        )

    def clamp_position(self, x: float, y: float, radius: float) -> tuple[float, float]:
        """Bloque un agent dans les limites de l'environnement (murs durs)."""
        x = max(radius, min(self.width - radius, x))
        y = max(radius, min(self.height - radius, y))
        return x, y

    def is_valid_spawn(self, x: float, y: float, radius: float) -> bool:
        """Vérifie que la position de spawn est valide :
        - Hors zone de pénalité murale
        - Hors mur"""
        margin = radius + 5
        return (
            x > self.zone_width + margin
            and x < self.width - self.zone_width - margin
            and y > self.zone_width + margin
            and y < self.height - self.zone_width - margin
        )