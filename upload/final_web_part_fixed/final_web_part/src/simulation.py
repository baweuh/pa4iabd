"""
src/simulation.py — Boucle principale fixed timestep, population, métriques,
CSV logging, sauvegarde meilleur génome.
Implémente la sélection NEAT : tournoi, crossover, spéciation, population cap.
"""

from __future__ import annotations

import csv
import math
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .agent import Agent
from .config import SimConfig, NeatConfig
from .environment import Environment
from .genome import Genome, InnovationCounter


class Species:
    """Représente une espèce dans le cadre de la spéciation NEAT."""

    def __init__(self, species_id: int, representative: Agent) -> None:
        self.id = species_id
        self.representative = representative
        self.members: list[Agent] = []
        self.best_fitness: float = 0.0
        self.stagnation_count: int = 0
        self.total_fitness: float = 0.0

    def update_stats(self) -> None:
        """Recalcule les statistiques de l'espèce."""
        if not self.members:
            self.total_fitness = 0.0
            return
        self.total_fitness = sum(a.fitness for a in self.members)
        current_best = max(a.fitness for a in self.members)
        if current_best > self.best_fitness:
            self.best_fitness = current_best
            self.stagnation_count = 0
        else:
            self.stagnation_count += 1

    @property
    def adjusted_fitness(self) -> float:
        """Fitness ajusté par sharing (divisé par la taille de l'espèce)."""
        if not self.members:
            return 0.0
        return self.total_fitness / len(self.members)


class Simulation:
    """
    Boucle de simulation ALife — neuroévolution avec sélection NEAT.
    Sélection par tournoi, crossover, spéciation, population cap.
    """

    def __init__(self, cfg: SimConfig, output_dir: str = "output") -> None:
        self.cfg = cfg
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # RNG
        configured_seed = cfg.simulation.seed
        if configured_seed is None:
            seed_rng = random.Random()
            self.actual_seed = seed_rng.randrange(0, 2**31 - 1)
        else:
            self.actual_seed = int(configured_seed)
        self.rng = random.Random(self.actual_seed)

        print(f"[Simulation] Graine RNG utilisée : {self.actual_seed}")
        print(f"[Simulation] Pour reproduire ce run : ajoutez ?seed={self.actual_seed} à l'URL,")
        print(f"[Simulation] ou lancez avec --seed {self.actual_seed} / ALIFE_SEED={self.actual_seed}")

        # Réinitialiser le compteur d'innovation global
        InnovationCounter().reset()

        # Nombre d'inputs/outputs du réseau
        self.num_inputs = cfg.agents.num_rays * 2 + 1  # 33
        self.num_outputs = 2  # vx, vy

        # Environnement
        self.env = Environment(cfg.environment, self.rng)

        # Population
        self.agents: list[Agent] = []
        self._bootstrap_population()

        # Espèces
        self.species: list[Species] = []
        self._next_species_id = 0
        self._species_refresh_interval = 50  # ticks entre chaque réassignation d'espèces
        self._last_species_refresh = 0

        # État
        self.current_tick = 0
        self.total_reproductions = 0
        self.running = True
        self._generation = 0

        # Métriques
        self.record_apples = 0
        self.best_agent: Agent | None = None
        self.dead_lifespans: list[int] = []

        # CSV logging
        self._csv_path = self.output_dir / "metrics.csv"
        self._csv_file = None
        self._csv_writer = None
        self._init_csv()

        # Répertoire pour les génomes
        self.genome_dir = self.output_dir / "genomes"
        self.genome_dir.mkdir(parents=True, exist_ok=True)

    # ══════════════════════════════════════════════════════════════════
    #  INITIALISATION
    # ══════════════════════════════════════════════════════════════════

    def _bootstrap_population(self) -> None:
        """Crée la population initiale."""
        cfg_a = self.cfg.agents
        center_x = self.env.width / 2
        center_y = self.env.height / 2
        spread = min(self.env.safe_max_x, self.env.safe_max_y) / 3

        for _ in range(cfg_a.initial_population):
            genome = Genome(self.num_inputs, self.num_outputs, self.rng)
            angle = self.rng.uniform(0, 2 * math.pi)
            dist = self.rng.uniform(0, spread)
            x = center_x + dist * math.cos(angle)
            y = center_y + dist * math.sin(angle)
            x, y = self.env.clamp_position(x, y, cfg_a.agent_radius)

            agent = Agent(
                genome=genome,
                x=x,
                y=y,
                energy=cfg_a.bootstrap_initial_energy,
                cfg_agents=cfg_a,
                cfg_mutations=self.cfg.mutations,
                rng=self.rng,
                is_bootstrap=True,
            )
            self.agents.append(agent)

        if self.agents:
            self.best_agent = self.agents[0]

    def _init_csv(self) -> None:
        self._csv_file = open(self._csv_path, "w", newline="", encoding="utf-8")
        self._csv_writer = csv.writer(self._csv_file)
        self._csv_writer.writerow([
            "tick", "population", "food_available", "record_apples",
            "avg_lifespan", "total_reproductions", "avg_network_size",
            "num_species", "best_fitness",
        ])
        self._csv_file.flush()

    # ══════════════════════════════════════════════════════════════════
    #  BOUCLE PRINCIPALE
    # ══════════════════════════════════════════════════════════════════

    def step(self) -> bool:
        if not self.running:
            return False

        # ── Raycasts + forward pass ──
        for agent in self.agents:
            if not agent.alive:
                continue
            inputs = agent.compute_raycasts(self.env)
            agent.think(inputs)

        # ── Mise à jour des positions ──
        for agent in self.agents:
            if not agent.alive:
                continue
            agent.move(self.env)
            agent.tick()

        # ── Contact pommes ──
        self._check_food_collision()

        # ── Drain énergétique ──
        for agent in self.agents:
            if not agent.alive:
                continue
            agent.apply_energy_drain(self.env)

        # ── Reproduction NEAT ──
        self._check_reproduction()

        # ── Mort ──
        self._check_death()

        # ── Respawn pommes ──
        self.env.respawn_apples(self.current_tick)

        # ── Refresh espèces périodiquement ──
        if self.current_tick - self._last_species_refresh >= self._species_refresh_interval:
            self._refresh_species()
            self._last_species_refresh = self.current_tick

        # ── Métriques ──
        self.current_tick += 1
        if self.current_tick % self.cfg.simulation.log_interval == 0:
            self._log_metrics()

        # ── Population critique → injecter des agents aléatoires ──
        if len(self.agents) < 5 and self.current_tick > 200:
            self._inject_random_agents(5)

        # ── Extinction → re-seeding ──
        if len(self.agents) == 0:
            self._handle_extinction()
            return False

        return True

    # ══════════════════════════════════════════════════════════════════
    #  SOUS-ÉTAPES
    # ══════════════════════════════════════════════════════════════════

    def _check_food_collision(self) -> None:
        if not self.agents:
            return

        agent_radius = self.cfg.agents.agent_radius
        food_radius = self.cfg.agents.food_radius
        eat_dist_sq = (agent_radius + food_radius) ** 2

        active_indices = [i for i, a in enumerate(self.env.apples) if a.respawn_at_tick < 0]
        if not active_indices:
            return

        food_pos = np.array([[self.env.apples[i].x, self.env.apples[i].y] for i in active_indices])

        for agent in self.agents:
            if not agent.alive:
                continue
            dx = agent.x - food_pos[:, 0]
            dy = agent.y - food_pos[:, 1]
            dists_sq = dx * dx + dy * dy

            closest = np.argmin(dists_sq)
            if dists_sq[closest] <= eat_dist_sq:
                real_idx = active_indices[closest]
                agent.eat(self.cfg.environment.food_energy)
                self.env.eat_apple(real_idx, self.current_tick)
                self._update_best_agent(agent)
                food_pos = np.delete(food_pos, closest, axis=0)
                active_indices.pop(closest)
                if not active_indices:
                    break

    def _check_reproduction(self) -> None:
        """
        Reproduction basée sur le fitness NEAT :
        1. Vérifier le population cap
        2. Sélection par tournoi parmi les agents éligibles
        3. Crossover + mutation pour créer l'enfant
        4. Cooldown de reproduction par agent
        """
        cfg_a = self.cfg.agents
        neat_cfg = self.cfg.neat

        # Population cap
        if len(self.agents) >= cfg_a.max_population:
            return

        # Intervalle de reproduction (pas tous les ticks)
        if self.current_tick % neat_cfg.reproduction_interval != 0:
            return

        # Agents éligibles (vivants, assez d'énergie, cooldown OK)
        eligible = [a for a in self.agents if a.alive and a.can_reproduce(self.current_tick)]
        if len(eligible) < 2:
            return

        # Nombre d'enfants à créer (pour maintenir la population)
        target_pop = cfg_a.max_population
        current_pop = len(self.agents)
        deficit = target_pop - current_pop
        # Créer quelques enfants par cycle de reproduction
        num_children = min(max(1, deficit // 5), 5)

        # Trier par fitness pour la sélection
        eligible.sort(key=lambda a: a.fitness, reverse=True)

        new_agents: list[Agent] = []
        for _ in range(num_children):
            if len(eligible) < 2:
                break

            # Sélection par tournoi
            parent1 = self._tournament_select(eligible, neat_cfg.tournament_size)

            # Décider si on fait un croisement interspécifique
            if self.rng.random() < neat_cfg.interspecies_mate_rate and len(eligible) >= 2:
                # Parent2 d'une espèce différente
                candidates = [a for a in eligible if a.species_id != parent1.species_id]
                if candidates:
                    parent2 = self._tournament_select(candidates, neat_cfg.tournament_size)
                else:
                    parent2 = self._tournament_select(eligible, neat_cfg.tournament_size)
            else:
                # Parent2 de la même espèce (préféré)
                same_species = [a for a in eligible if a.species_id == parent1.species_id and a is not parent1]
                if same_species and len(same_species) >= 1:
                    parent2 = self._tournament_select(same_species, max(1, neat_cfg.tournament_size - 1))
                else:
                    parent2 = self._tournament_select(eligible, neat_cfg.tournament_size)

            # Crossover ou clone + mutation
            if (self.rng.random() < neat_cfg.crossover_rate
                    and parent1 is not parent2):
                child_genome = Genome.crossover(
                    parent1.genome, parent2.genome,
                    parent1.fitness, parent2.fitness,
                    neat_cfg, self.rng,
                )
                child_genome.mutate(self.cfg.mutations)
            else:
                # Reproduction asexuée du meilleur parent
                child_genome = parent1.genome.deep_copy()
                child_genome.mutate(self.cfg.mutations)

            # Mettre à jour le parent (coût énergétique + cooldown)
            parent1.energy = cfg_a.parent_energy_after_repro
            parent1.last_reproduction_tick = self.current_tick
            parent1.children_count += 1

            # Position de l'enfant
            child_x, child_y = parent1._find_spawn_position(self.env, cfg_a.spawn_radius_child)

            child = Agent(
                genome=child_genome,
                x=child_x,
                y=child_y,
                energy=cfg_a.child_initial_energy,
                cfg_agents=cfg_a,
                cfg_mutations=self.cfg.mutations,
                rng=self.rng,
                is_bootstrap=False,
            )
            # L'enfant hérite de l'espèce du parent1
            child.species_id = parent1.species_id

            new_agents.append(child)
            self.total_reproductions += 1
            self._generation += 1

        self.agents.extend(new_agents)

    def _tournament_select(self, candidates: list[Agent], k: int) -> Agent:
        """Sélection par tournoi : choisir k agents aléatoires, retourner le meilleur."""
        k = min(k, len(candidates))
        if k <= 0:
            return candidates[0]
        tournament = self.rng.sample(candidates, k)
        return max(tournament, key=lambda a: a.fitness)

    # ══════════════════════════════════════════════════════════════════
    #  SPÉCIATION
    # ══════════════════════════════════════════════════════════════════

    def _refresh_species(self) -> None:
        """Réassigne les agents aux espèces et met à jour les représentants."""
        neat_cfg = self.cfg.neat
        alive_agents = [a for a in self.agents if a.alive]

        # Réinitialiser les espèces
        for sp in self.species:
            sp.members = []
            sp.update_stats()

        # Assigner chaque agent à l'espèce la plus proche
        for agent in alive_agents:
            assigned = False
            for sp in self.species:
                dist = agent.genome.compatibility_distance(sp.representative.genome, neat_cfg)
                if dist < neat_cfg.species_threshold:
                    sp.members.append(agent)
                    agent.species_id = sp.id
                    assigned = True
                    break

            if not assigned:
                # Créer une nouvelle espèce
                new_sp = Species(self._next_species_id, agent)
                new_sp.members.append(agent)
                agent.species_id = new_sp.id
                self.species.append(new_sp)
                self._next_species_id += 1

        # Mettre à jour les représentants (le membre le plus fit)
        for sp in self.species:
            if sp.members:
                sp.representative = max(sp.members, key=lambda a: a.fitness)
                sp.update_stats()

        # Éliminer les espèces vides ou stagnantes depuis trop longtemps
        self.species = [sp for sp in self.species if sp.members and sp.stagnation_count < 30]

        # Si toutes les espèces sont éliminées (rare), recréer
        if not self.species and alive_agents:
            best = max(alive_agents, key=lambda a: a.fitness)
            new_sp = Species(self._next_species_id, best)
            for a in alive_agents:
                dist = a.genome.compatibility_distance(best.genome, neat_cfg)
                if dist < neat_cfg.species_threshold * 1.5:  # Seuil plus large pour la recovery
                    new_sp.members.append(a)
                    a.species_id = new_sp.id
            if not new_sp.members:
                new_sp.members.append(best)
                best.species_id = new_sp.id
            self.species.append(new_sp)
            self._next_species_id += 1

    # ══════════════════════════════════════════════════════════════════
    #  MORT
    # ══════════════════════════════════════════════════════════════════

    def _check_death(self) -> None:
        survivors: list[Agent] = []
        for agent in self.agents:
            if agent.is_dead():
                self.dead_lifespans.append(agent.age)
            else:
                survivors.append(agent)
        self.agents = survivors

        if self.best_agent is None or not self.best_agent.alive:
            if self.agents:
                self.best_agent = max(self.agents, key=lambda a: a.fitness)

    def _update_best_agent(self, agent: Agent) -> None:
        if agent.food_eaten > self.record_apples:
            self.record_apples = agent.food_eaten
            self.best_agent = agent
            filename = f"best_genome_tick_{self.current_tick}_apples_{agent.food_eaten}.json"
            filepath = self.genome_dir / filename
            filepath.write_text(agent.genome.to_json(), encoding="utf-8")

    # ══════════════════════════════════════════════════════════════════
    #  MÉTRIQUES
    # ══════════════════════════════════════════════════════════════════

    def _log_metrics(self) -> None:
        if self.dead_lifespans:
            avg_lifespan = sum(self.dead_lifespans) / len(self.dead_lifespans)
            self.dead_lifespans.clear()
        else:
            avg_lifespan = 0.0

        if self.agents:
            avg_net_size = sum(a.network.network_size for a in self.agents) / len(self.agents)
            best_fit = max(a.fitness for a in self.agents)
        else:
            avg_net_size = 0.0
            best_fit = 0.0

        if self._csv_writer is not None:
            self._csv_writer.writerow([
                self.current_tick,
                len(self.agents),
                self.env.food_available,
                self.record_apples,
                round(avg_lifespan, 2),
                self.total_reproductions,
                round(avg_net_size, 2),
                len(self.species),
                round(best_fit, 2),
            ])
            self._csv_file.flush()

    # ══════════════════════════════════════════════════════════════════
    #  FIN DE SIMULATION
    # ══════════════════════════════════════════════════════════════════

    def _inject_random_agents(self, count: int) -> None:
        """Injecte des agents aléatoires quand la population est critique.
        Ces agents héritent de mutations du meilleur génome vu + du hasard.
        """
        cfg_a = self.cfg.agents
        center_x = self.env.width / 2
        center_y = self.env.height / 2
        spread = min(self.env.safe_max_x, self.env.safe_max_y) / 3

        for _ in range(count):
            # 50% chance : clone du meilleur agent vu (avec mutations fortes)
            # 50% chance : génome totalement aléatoire
            if self.best_agent and self.rng.random() < 0.5:
                child_genome = self.best_agent.genome.deep_copy()
            else:
                child_genome = Genome(self.num_inputs, self.num_outputs, self.rng)

            # Appliquer des mutations fortes pour la diversité
            for __ in range(3):
                child_genome.mutate(self.cfg.mutations)

            angle = self.rng.uniform(0, 2 * math.pi)
            dist = self.rng.uniform(0, spread)
            x = center_x + dist * math.cos(angle)
            y = center_y + dist * math.sin(angle)
            x, y = self.env.clamp_position(x, y, cfg_a.agent_radius)

            agent = Agent(
                genome=child_genome,
                x=x,
                y=y,
                energy=cfg_a.bootstrap_initial_energy,
                cfg_agents=cfg_a,
                cfg_mutations=self.cfg.mutations,
                rng=self.rng,
                is_bootstrap=False,
            )
            self.agents.append(agent)

    def _handle_extinction(self) -> None:
        self.running = False
        self._log_metrics()
        timestamp = datetime.now(timezone.utc).isoformat()
        msg = (
            f"[{timestamp}] EXTINCTION — Population = 0 au tick {self.current_tick}. "
            f"Record pommes : {self.record_apples}. Graine : {self.actual_seed}. "
            f"Générations : {self._generation}."
        )
        print(msg)
        log_path = self.output_dir / "simulation.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(msg + "\n")

    def shutdown(self) -> None:
        self.running = False
        if self._csv_file is not None:
            self._csv_file.close()
        timestamp = datetime.now(timezone.utc).isoformat()
        msg = (
            f"[{timestamp}] INTERRUPTION MANUELLE — Tick {self.current_tick}. "
            f"Record pommes : {self.record_apples}. Graine : {self.actual_seed}. "
            f"Générations : {self._generation}."
        )
        print(msg)
        log_path = self.output_dir / "simulation.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(msg + "\n")