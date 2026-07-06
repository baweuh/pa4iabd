"""
src/agent.py — Agent : énergie, cycle de vie, raycasts 16×360°, déplacement,
fitness, reproduction avec cooldown.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from .config import AgentsConfig, MutationsConfig
from .environment import Environment
from .genome import Genome, InnovationCounter
from .network import NeuralNetwork

if TYPE_CHECKING:
    pass


class Agent:
    """
    Un agent dans la simulation ALife.
    Propriétés physiques, cycle de vie, système d'énergie,
    perception via 16 raycasts 360°.
    """

    def __init__(
        self,
        genome: Genome,
        x: float,
        y: float,
        energy: float,
        cfg_agents: AgentsConfig,
        cfg_mutations: MutationsConfig,
        rng: random.Random,
        is_bootstrap: bool = False,
    ) -> None:
        self.genome = genome
        self.network = NeuralNetwork(genome)
        self.x = x
        self.y = y
        self.vx = 0.0
        self.vy = 0.0
        self.energy = energy
        self.cfg = cfg_agents
        self.cfg_mut = cfg_mutations
        self.rng = rng

        # Cycle de vie
        self.age = 0
        self.alive = True
        self.is_bootstrap = is_bootstrap

        # Compteurs
        self.food_eaten = 0
        self.children_count = 0

        # Reproduction
        self.last_reproduction_tick: int = -999  # Permet de reproduire immédiatement au bootstrap

        # Espèce (assignée par la simulation)
        self.species_id: int = -1

        # Raycasts (pour le rendu)
        self.rays: list[tuple[float, float, float]] = []

        # Inputs du réseau : 33 (16 rays × 2 + 1 énergie)
        self.input_size = cfg_agents.num_rays * 2 + 1

    # ══════════════════════════════════════════════════════════════════
    #  FITNESS
    # ══════════════════════════════════════════════════════════════════

    @property
    def fitness(self) -> float:
        """
        Fitness de l'agent. Principalement basé sur la nourriture mangée,
        avec un léger bonus de survie pour éviter que les agents meurent
        trop vite sans avoir exploré.
        """
        food_bonus = self.food_eaten * 100.0
        survival_bonus = self.age * 0.01
        # Petit bonus pour l'énergie restante (montre l'efficacité)
        efficiency_bonus = max(0, self.energy) * 2.0
        return food_bonus + survival_bonus + efficiency_bonus

    # ══════════════════════════════════════════════════════════════════
    #  RAYCASTS  (input encoding corrigé)
    # ══════════════════════════════════════════════════════════════════

    def compute_raycasts(self, env: Environment) -> np.ndarray:
        """
        Calcule 16 raycasts répartis uniformément à 360°.
        Retourne les inputs du réseau (33 valeurs) : 16 × (distance + type) + 1 énergie.

        Encodage corrigé par ray :
        - inputs[i*2]   = distance normalisée [0→1] du hit le plus proche
        - inputs[i*2+1] = type : 0.0 = rien | 0.5 = pomme | 1.0 = mur
        """
        num_rays = self.cfg.num_rays
        ray_range = self.genome.ray_range
        food_radius = self.cfg.food_radius

        inputs = np.zeros(self.input_size, dtype=np.float64)
        self.rays = []
        step = 2.0 * math.pi / num_rays

        max_dist_sq = (ray_range + food_radius + 5) ** 2
        active_apples = [
            a for a in env.apples
            if a.respawn_at_tick < 0
            and (a.x - self.x) ** 2 + (a.y - self.y) ** 2 <= max_dist_sq
        ]

        for i in range(num_rays):
            angle = i * step
            dx = math.cos(angle)
            dy = math.sin(angle)

            # ── Intersection mur la plus proche ──
            wall_t = ray_range + 1.0
            if dx < -1e-9:
                t = -self.x / dx
                if 0 < t < wall_t:
                    wall_t = t
            if dx > 1e-9:
                t = (env.width - self.x) / dx
                if 0 < t < wall_t:
                    wall_t = t
            if dy < -1e-9:
                t = -self.y / dy
                if 0 < t < wall_t:
                    wall_t = t
            if dy > 1e-9:
                t = (env.height - self.y) / dy
                if 0 < t < wall_t:
                    wall_t = t

            # ── Intersection pomme la plus proche ──
            food_t = ray_range + 1.0
            hit_food = False
            detect_r_sq = (food_radius + 10) ** 2

            for apple in active_apples:
                vfx = apple.x - self.x
                vfy = apple.y - self.y
                proj = vfx * dx + vfy * dy
                if proj <= 0 or proj >= min(wall_t, food_t):
                    continue
                px = self.x + proj * dx
                py = self.y + proj * dy
                if (px - apple.x) ** 2 + (py - apple.y) ** 2 <= detect_r_sq:
                    food_t = proj
                    hit_food = True

            # ── Résolution + encodage CORRIGÉ ──
            if hit_food and food_t < wall_t:
                # Pomme visible (plus proche que le mur)
                dist = food_t
                kind = 0.5
                inputs[i * 2] = food_t / ray_range      # distance normalisée
                inputs[i * 2 + 1] = 0.5                   # type = pomme
            elif wall_t <= ray_range:
                # Mur visible
                dist = wall_t
                kind = 1.0
                inputs[i * 2] = wall_t / ray_range       # distance normalisée
                inputs[i * 2 + 1] = 1.0                    # type = mur
            else:
                # Rien de visible
                dist = ray_range
                kind = 0.0
                inputs[i * 2] = 1.0                        # distance max
                inputs[i * 2 + 1] = 0.0                    # type = rien

            self.rays.append((
                self.x + dist * dx,
                self.y + dist * dy,
                kind,
            ))

        # Input 32 : énergie normalisée [0.0 → 1.0]
        inputs[num_rays * 2] = min(self.energy / self.cfg.max_energy, 1.0)

        return inputs

    # ══════════════════════════════════════════════════════════════════
    #  DÉPLACEMENT
    # ══════════════════════════════════════════════════════════════════

    def move(self, env: Environment) -> None:
        max_speed = self.cfg.max_speed

        speed = math.sqrt(self.vx ** 2 + self.vy ** 2)
        if speed > max_speed:
            scale = max_speed / speed
            self.vx *= scale
            self.vy *= scale

        new_x = self.x + self.vx
        new_y = self.y + self.vy

        radius = self.cfg.agent_radius
        self.x, self.y = env.clamp_position(new_x, new_y, radius)

    def think(self, inputs: np.ndarray) -> None:
        outputs = self.network.activate(inputs)
        self.vx = outputs[0]
        self.vy = outputs[1]

    # ══════════════════════════════════════════════════════════════════
    #  ÉNERGIE
    # ══════════════════════════════════════════════════════════════════

    def apply_energy_drain(self, env: Environment) -> None:
        """Applique le drain énergétique : base + pénalité vision longue + zone pénalité."""
        vision_cost = self.genome.ray_range / 150.0
        drain = self.cfg.base_drain_rate * vision_cost
        drain += env.wall_penalty_drain(self.x, self.y)
        self.energy -= drain

    def eat(self, food_energy: float) -> None:
        self.energy += food_energy
        self.food_eaten += 1

    # ══════════════════════════════════════════════════════════════════
    #  CYCLE DE VIE
    # ══════════════════════════════════════════════════════════════════

    def is_dead(self) -> bool:
        if self.energy <= 0:
            return True
        if self.age >= self.cfg.max_lifespan:
            return True
        return False

    def is_dying(self) -> bool:
        return self.age >= self.cfg.max_lifespan - self.cfg.lifespan_warning_ticks

    def can_reproduce(self, current_tick: int) -> bool:
        """Vérifie si l'agent peut se reproduire : énergie + cooldown."""
        if self.energy < self.cfg.reproduction_threshold:
            return False
        if current_tick - self.last_reproduction_tick < self.cfg.reproduction_cooldown:
            return False
        return True

    # ══════════════════════════════════════════════════════════════════
    #  REPRODUCTION ASEXUÉE  (clone + mutate — utilisé comme fallback)
    # ══════════════════════════════════════════════════════════════════

    def reproduce_asexual(self, env: Environment, current_tick: int) -> Agent:
        """Crée un enfant par reproduction asexuée (clone + mutations)."""
        child_genome = self.genome.deep_copy()
        child_genome.mutate(self.cfg_mut)

        self.energy = self.cfg.parent_energy_after_repro
        self.last_reproduction_tick = current_tick
        self.children_count += 1

        spawn_radius = self.cfg.spawn_radius_child
        child_x, child_y = self._find_spawn_position(env, spawn_radius)

        child = Agent(
            genome=child_genome,
            x=child_x,
            y=child_y,
            energy=self.cfg.child_initial_energy,
            cfg_agents=self.cfg,
            cfg_mutations=self.cfg_mut,
            rng=self.rng,
            is_bootstrap=False,
        )

        return child

    def _find_spawn_position(self, env: Environment, spawn_radius: float) -> tuple[float, float]:
        for _ in range(50):
            angle = self.rng.uniform(0, 2 * math.pi)
            dist = self.rng.uniform(50, spawn_radius)
            child_x = self.x + dist * math.cos(angle)
            child_y = self.y + dist * math.sin(angle)

            if env.is_valid_spawn(child_x, child_y, self.cfg.agent_radius):
                child_x, child_y = env.clamp_position(child_x, child_y, self.cfg.agent_radius)
                return child_x, child_y
        return self.x, self.y

    # ══════════════════════════════════════════════════════════════════
    #  UTILITAIRES
    # ══════════════════════════════════════════════════════════════════

    def tick(self) -> None:
        self.age += 1