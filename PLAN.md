# Plan d'implémentation — ALife Neuroevolution

## Phase 1 — Fondations ✅ / 🔄 / ⬜
- [ ] config.py (SimConfig dataclass + chargement YAML)
- [ ] config/default.yaml (tous les paramètres)
- [ ] tests/test_config.py

## Phase 2 — Génome ✅
- [x] NodeGene, ConnectionGene
- [x] Genome (init fully connected 33×2, clone, sérialisation JSON)
- [x] Innovation counter global
- [x] 5 mutations (add_node, add_connection avec DFS, remove_node,
        remove_connection, mutate_weights)
- [x] tests/test_genome.py (mutations valides, pas de cycle, IDs uniques)

## Phase 3 — Réseau de neurones ✅
- [x] Topological sort (cache à l'init)
- [x] Forward pass feedforward
- [x] Normalisation output vitesse
- [x] tests/test_network.py (forward déterministe, cycle détecté)

## Phase 4 — Environnement ✅
- [x] Apple (spawn zone safe, respawn aléatoire)
- [x] Zone pénalité gradient
- [x] tests/test_environment.py (pommes hors zone penalty, gradient correct)

## Phase 5 — Agent ✅
- [x] Raycasts (16 rays, first-hit, (distance, type))
- [x] Énergie (drain/tick, manger, reproduction, mort)
- [x] Cycle de vie complet (naissance, reproduction, mort famine/vieillesse)
- [x] tests/test_agent.py

## Phase 6 — Simulation (boucle principale) ✅
- [x] Fixed timestep loop (découplé rendu)
- [x] Gestion population (spawn, mort, extinction propre)
- [x] CSV logging continu
- [x] Sauvegarde meilleur génome
- [x] tests/test_simulation.py (tick order, CSV produit)
- [x] Respawn différé des pommes (patchs rétro Phase 4/5, CDC §5.2)

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