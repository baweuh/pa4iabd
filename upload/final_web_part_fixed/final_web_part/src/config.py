"""
src/config.py — Chargement YAML + dataclass typée pour toute la configuration.
Zéro valeur hardcodée dans le code source (CDC §10).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


# ── Dataclasses imbriquées ────────────────────────────────────────────

@dataclass
class EnvironmentConfig:
    env_width: int = 800
    env_height: int = 800
    zone_width: float = 60.0
    zone_max_drain: float = 0.05
    food_count: int = 30
    food_respawn_delay: int = 150
    food_energy: float = 1.0


@dataclass
class AgentsConfig:
    initial_population: int = 30
    max_population: int = 80
    max_speed: float = 2.0
    base_drain_rate: float = 0.005
    bootstrap_initial_energy: float = 4.0
    child_initial_energy: float = 2.0
    reproduction_threshold: float = 5.0
    parent_energy_after_repro: float = 1.0
    max_lifespan: int = 10000
    lifespan_warning_ticks: int = 500
    agent_radius: float = 10.0
    food_radius: float = 7.0
    ray_max_range: float = 200.0
    num_rays: int = 16
    spawn_radius_child: float = 75.0
    max_energy: float = 10.0
    reproduction_cooldown: int = 50
    parent_selection_fraction: float = 0.4


@dataclass
class MutationsConfig:
    mutate_weights_prob: float = 0.80
    weight_perturb_prob: float = 0.15
    weight_sigma: float = 0.2
    weight_reset_prob: float = 0.05
    add_connection_prob: float = 0.05
    add_node_prob: float = 0.03
    remove_connection_prob: float = 0.05
    remove_node_prob: float = 0.02


@dataclass
class NeatConfig:
    tournament_size: int = 3
    species_threshold: float = 3.0
    compatibility_excess_coeff: float = 1.0
    compatibility_disjoint_coeff: float = 1.0
    compatibility_weight_coeff: float = 0.4
    crossover_rate: float = 0.75
    interspecies_mate_rate: float = 0.1
    elite_fraction: float = 0.1
    reproduction_interval: int = 10


@dataclass
class SimulationConfig:
    tick_rate: int = 60
    render_fps: int = 60
    log_interval: int = 100
    # seed = None (ou null en YAML) → graine aléatoire à chaque démarrage.
    # Permet de garantir une expérimentation différente à chaque run.
    # Pour reproduire un run précis, fixer la graine via CLI (--seed N),
    # variable d'environnement (ALIFE_SEED=N) ou paramètre URL (?seed=N).
    seed: Optional[int] = None
    headless: bool = False


@dataclass
class SimConfig:
    """Configuration racine — agrège toutes les sous-sections YAML."""
    environment: EnvironmentConfig = field(default_factory=EnvironmentConfig)
    agents: AgentsConfig = field(default_factory=AgentsConfig)
    mutations: MutationsConfig = field(default_factory=MutationsConfig)
    neat: NeatConfig = field(default_factory=NeatConfig)
    simulation: SimulationConfig = field(default_factory=SimulationConfig)


# ── Chargement ───────────────────────────────────────────────────────

def _load_yaml(path: str | Path) -> dict[str, Any]:
    """Charge un fichier YAML et retourne un dict."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_dataclass(cls: type, data: dict[str, Any] | None) -> Any:
    """Construit une dataclass à partir d'un dict, en ignorant les clés inconnues."""
    if data is None:
        return cls()
    valid = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
    return cls(**valid)


def load_config(yaml_path: str | Path | None = None) -> SimConfig:
    """
    Charge la configuration depuis un fichier YAML.
    Si yaml_path est None, cherche config/default.yaml relatif au répertoire courant
    puis relatif à ce fichier.
    """
    if yaml_path is None:
        candidates = [
            Path("config/default.yaml"),
            Path(__file__).resolve().parent.parent / "config" / "default.yaml",
        ]
        for c in candidates:
            if c.exists():
                yaml_path = c
                break
        else:
            raise FileNotFoundError(
                "Fichier de configuration non trouvé. "
                "Passez --config <chemin> ou placez config/default.yaml."
            )

    raw = _load_yaml(yaml_path)

    return SimConfig(
        environment=_build_dataclass(EnvironmentConfig, raw.get("environment")),
        agents=_build_dataclass(AgentsConfig, raw.get("agents")),
        mutations=_build_dataclass(MutationsConfig, raw.get("mutations")),
        neat=_build_dataclass(NeatConfig, raw.get("neat")),
        simulation=_build_dataclass(SimulationConfig, raw.get("simulation")),
    )