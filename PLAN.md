# Plan d'implémentation — ALife Neuroevolution

## Phase 1 — Fondations ✅
- [x] config.py (SimConfig dataclass + chargement YAML)
- [x] config/default.yaml (tous les paramètres)
- [x] tests/test_config.py

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
- [x] CSV logger exposé en API publique (open_csv_logger / close_csv_logger) → Phase 8

## Phase 7 — Rendu ✅
- [x] Renderer Pygame (agents, pommes, zone penalty, HUD)
- [x] Raycasts visibles (reconstruits depuis Agent.sense(), zéro accès privé)
- [x] Gradient couleur énergie (rouge→jaune→vert) + UI boutons vitesse
- [x] tests/test_renderer_smoke_500_ticks_with_ui.py (5 tests, SDL dummy)
- [x] Mode headless (renderer.py non instancié) → livré Phase 8 (main.py CLI)
- [x] Indicateur visuel fin de vie (end_of_life_ticks derniers ticks) → livré Phase 8

## Phase 8 — Intégration ✅
- [x] main.py (CLI argparse : --mode/--seed/--ticks/--config, fallback YAML)
- [x] Mode visual (Renderer) + mode headless (boucle + progress + CSV)
- [x] Indicateur fin de vie (override gradient → rouge, piloté par config)
- [x] tests/test_main_cli_modes.py (9 tests : modes, overrides, déterminisme)
- [x] PHASE8.md (architecture + décisions)

## Phase 9 — AWS + Dashboard ⬜
- [ ] S3 (upload ZIP + génomes)
- [ ] DynamoDB (métriques)
- [ ] Amplify (dashboard)

## Branche poc2.2 — Dynamique évolutive (investigation) ✅
> POC hors numérotation des phases : rendre l'évolution *adaptative*, pas seulement
> viable. Journal complet dans `docs/Audits/AUDIT-poc2.2-v3.md` (ÉTAPES 0–10).
- [x] Instrumentation évolutive (spéciation, 6 colonnes CSV, sondes
        `tools/steer_probe.py` + `tools/run_and_probe.py`)
- [x] 5 correctifs architecturaux dc20330 (égocentrisme B3a, input 2D 49, fécondité
        ∝ énergie B3b, élitisme, clamp poids I2) → règlent la **viabilité**
- [x] Diagnostic (audit v3) : blocage = sélection ≪ mutation + dérive, PAS le repère
        de sortie. Preuve = sonde comportementale (champion anti-fourrageur r=−0,17)
- [x] Campagne leviers (mutation / drain / max_energy / food / move_cost) : aucun
        réglage paramétrique ne robustifie — chaque régime rebrasse quel seed gagne
- [x] Changement **structurel** `agent.apples_per_offspring` (défaut 0.0 = legacy ;
        >0 = fécondité ∝ pommes cumulées) + `agent.move_cost`
- [x] Résultat : `config/apple_repro_bigpop.yaml` = 1ʳᵉ émergence de fourrage
        **robuste (3 seeds) ET stable (30k)** : 86/84/56 % fourrageurs
- [ ] ⬜ Décision : promouvoir `apple_repro_bigpop` en défaut ? (change monde/pop)
- [ ] ⬜ Validation élargie (N seeds) + réglage de K pour remonter seed 123

## Branche poc2.3 — Capteurs 67 + visualisation + relance structurelle ✅
> POC hors numérotation. Journal complet dans `docs/Audits/AUDIT-poc2.3.md`.
- [x] Capteurs 67 inputs : apple_dist/wall_dist séparés (4 canaux/rayon),
        proprioception (actual_speed), apples_in_view (fa2656e)
- [x] Panneau réseau (touche N) : nœuds par groupe sensoriel, connexions par
        signe de poids, titre `hidden:N` — évolution structurelle observable
- [x] Sparkline forage rate, HUD 3 lignes (Repro/Gen), fullscreen F11
- [x] Expérience relance structurelle (add_node_rate 0,25 / apples_per_offspring
        3,0, pop défaut) : **falsifiée**. Run `logs/2026-07-07_142103` 30k →
        0 neurone caché, record_apples fige à 53, dérive neutre (gen_dist ×34,
        51 espèces). Le levier poc2.2 était la **population** (bigpop 200→400),
        pas le taux de mutation. `config/default.yaml` remis à l'état canonique.
- [ ] ⬜ Prochaine piste = mécanisme, pas paramètre : grande population OU tâche
        exigeant de la non-linéarité OU crossover/pression de spéciation