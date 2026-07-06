# /// script
# dependencies = ["pygame-ce", "pyyaml", "numpy"]
# ///
"""
main.py — Point d'entrée de la simulation ALife.
CDC §9 : Parsing args CLI (--headless, --config), lancement simulation.

Usage local:
    python main.py                  # mode interactif (rendu Pygame)
    python main.py --headless       # mode headless (pas de rendu)
    python main.py --config path    # fichier YAML personnalisé

Usage web (pygbag):
    pygbag . --build
"""

from __future__ import annotations

import argparse
import os
import sys

# Ajouter le répertoire parent au path pour les imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import load_config
from src.simulation import Simulation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simulation ALife — Neuroévolution continue",
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        help="Chemin vers le fichier YAML de configuration (défaut : config/default.yaml)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Désactive le rendu Pygame (mode headless, max ticks/sec CPU)",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="output",
        help="Répertoire de sortie pour CSV, génomes, logs (défaut : output)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Graine RNG. Si non spécifié, la valeur du YAML est utilisée. "
             "Si le YAML indique null/absent, une graine aléatoire est tirée.",
    )
    return parser.parse_args()


def _resolve_seed(cli_seed):
    """Détermine la graine RNG effective.

    Priorité (décroissante) :
      1. Argument CLI --seed N  (cli_seed non None)
      2. Variable d'environnement ALIFE_SEED=N
      3. Valeur du YAML (cfg.simulation.seed, éventuellement None)
      4. None → une graine aléatoire sera tirée dans Simulation.__init__

    Retourne : int | None  (None signifie « graine aléatoire »).
    """
    if cli_seed is not None:
        return int(cli_seed)

    env_seed = os.environ.get("ALIFE_SEED")
    if env_seed not in (None, "", "null", "None"):
        try:
            return int(env_seed)
        except ValueError:
            print(f"[main] ALIFE_SEED='{env_seed}' invalide, ignoré.")

    # Laisser Simulation.__init__ gérer le cas None (graine aléatoire)
    return None


def run_headless(sim: Simulation) -> None:
    """Mode headless : pas de rendu, maximum de ticks par seconde CPU.
    CDC §6.1 : accélérer la simulation = avancer le temps simulé plus vite,
    sans modifier les valeurs énergétiques par tick."""
    print(f"[Headless] Démarrage — {len(sim.agents)} agents, {sim.env.food_available} pommes")
    print("[Headless] Ctrl+C pour arrêter")

    try:
        while sim.running:
            sim.step()
            # Afficher un point de progression toutes les 1000 ticks
            if sim.current_tick % 1000 == 0:
                print(
                    f"  tick={sim.current_tick}  pop={len(sim.agents)}  "
                    f"food={sim.env.food_available}  record={sim.record_apples}"
                )
    except KeyboardInterrupt:
        sim.shutdown()


def run_gui(sim: Simulation) -> None:
    """Mode interactif avec rendu Pygame.
    CDC §6.1 :
    - Temps réel : ~1 tick/frame, FPS cible = 60
    - Accéléré : N > 1 ticks par frame
    """
    import pygame
    from src.renderer import Renderer

    renderer = Renderer(
        env_cfg=sim.cfg.environment,
        agent_cfg=sim.cfg.agents,
        sim_cfg=sim.cfg.simulation,
    )

    ticks_per_frame = 1
    paused = False
    target_fps = sim.cfg.simulation.render_fps

    print(f"[GUI] Démarrage — {len(sim.agents)} agents, {sim.env.food_available} pommes")
    print("[GUI] ESPACE=pause  HAUT/BAS=vitesse  ESC=quitter")

    try:
        while sim.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    sim.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_SPACE:
                        paused = not paused
                    elif event.key == pygame.K_UP:
                        ticks_per_frame = min(ticks_per_frame * 2, 64)
                    elif event.key == pygame.K_DOWN:
                        ticks_per_frame = max(ticks_per_frame // 2, 1)
                    elif event.key == pygame.K_ESCAPE:
                        sim.running = False

            if not paused and sim.running:
                for _ in range(ticks_per_frame):
                    if not sim.step():
                        break

            if sim.running:
                renderer.render(sim, ticks_per_frame)
                renderer.tick_clock(target_fps)

    except KeyboardInterrupt:
        pass
    finally:
        sim.shutdown()
        renderer.quit()


def main() -> None:
    # Environnement web (Pyodide/pygbag) : pas d'args CLI, forcer le mode GUI.
    # sys.platform == 'emscripten' (minuscules) en Pyodide ; on utilise aussi
    # la variable d'environnement PYODIDE=1 définie par web/index.html pour
    # une détection robuste.
    is_web = (
        "emscripten" in sys.platform.lower()
        or os.environ.get("PYODIDE") == "1"
    )

    if is_web:
        cfg = load_config(None)
        cfg.simulation.headless = False
        # Sur le web, la graine peut venir de ?seed=N dans l'URL.
        # web/index.html lit ce paramètre et l'injecte dans os.environ['ALIFE_SEED']
        # avant de lancer main.py. On laisse _resolve_seed gérer la priorité.
        cfg.simulation.seed = _resolve_seed(cli_seed=None)
        sim = Simulation(cfg, output_dir="/tmp/output")
        run_gui(sim)
        return

    args = parse_args()

    # Charger la configuration
    cfg = load_config(args.config)

    # Override headless via CLI
    if args.headless:
        cfg.simulation.headless = True

    # Override seed via CLI / ALIFE_SEED (priorité sur le YAML)
    resolved = _resolve_seed(args.seed)
    if resolved is not None:
        cfg.simulation.seed = resolved
    # Si resolved est None et cfg.simulation.seed est aussi None,
    # Simulation.__init__ tirera une graine aléatoire.

    # Créer la simulation
    sim = Simulation(cfg, output_dir=args.output)

    # Lancer le mode approprié
    if cfg.simulation.headless:
        run_headless(sim)
    else:
        run_gui(sim)


if __name__ == "__main__":
    main()