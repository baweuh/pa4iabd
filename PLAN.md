# Plan d'implémentation — ALife Neuroevolution

## Phase 1 — Fondations ✅ / 🔄 / ⬜
- [ ] config.py (SimConfig dataclass + chargement YAML)
- [ ] config/default.yaml (tous les paramètres)
- [ ] tests/test_config.py

## Phase 2 — Génome ⬜
- [ ] NodeGene, ConnectionGene
- [ ] Genome (init fully connected 33×2, clone, sérialisation JSON)
- [ ] Innovation counter global
- [ ] 5 mutations (add_node, add_connection avec DFS, remove_node,
        remove_connection, mutate_weights)
- [ ] tests/test_genome.py (mutations valides, pas de cycle, IDs uniques)

## Phase 3 — Réseau de neurones ⬜
- [ ] Topological sort (cache à l'init)
- [ ] Forward pass feedforward
- [ ] Normalisation output vitesse
- [ ] tests/test_network.py (forward déterministe, cycle détecté)

## Phase 4 — Environnement ⬜
- [ ] Apple (spawn zone safe, respawn aléatoire)
- [ ] Zone pénalité gradient
- [ ] tests/test_environment.py (pommes hors zone penalty, gradient correct)

## Phase 5 — Agent ⬜
- [ ] Raycasts (16 rays, first-hit, (distance, type))
- [ ] Énergie (drain/tick, manger, reproduction, mort)
- [ ] Cycle de vie complet (naissance, reproduction, mort famine/vieillesse)
- [ ] tests/test_agent.py

## Phase 6 — Simulation (boucle principale) ⬜
- [ ] Fixed timestep loop (découplé rendu)
- [ ] Gestion population (spawn, mort, extinction propre)
- [ ] CSV logging continu
- [ ] Sauvegarde meilleur génome
- [ ] tests/test_simulation.py (tick order, CSV produit)

## Phase 7 — Rendu ⬜
- [ ] Renderer Pygame (agents, pommes, zone penalty, HUD)
- [ ] Mode headless (renderer.py non instancié)
- [ ] Indicateur visuel fin de vie (500 derniers ticks)

## Phase 8 — Intégration ⬜
- [ ] main.py (CLI argparse)
- [ ] Test de smoke (simulation tourne 500 ticks sans crash)
- [ ] Calibration paramètres de base

## Phase 9 — AWS + Dashboard ⬜
- [ ] S3 (upload ZIP + génomes)
- [ ] DynamoDB (métriques)
- [ ] Amplify (dashboard)