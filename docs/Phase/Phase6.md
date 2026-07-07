# Phase 6 — Simulation (boucle principale + population) ✅

## Contexte

Phases 1–5 en place (`SimConfig`, `Genome`, `NeuralNetwork`, `Environment`/`Apple`,
`Agent`). Phase 6 assemble le tout dans une **simulation qui tourne** : driver
fixed-timestep découplé du rendu, gestion de population (spawn / naissance / mort /
extinction propre), logging CSV continu, et sauvegarde du meilleur génome quand le
record de pommes mangées est battu.

> Aucun fichier CDC v5 n'est présent dans le repo : le design est piloté par les
> invariants CLAUDE.md, l'énoncé du prompt et deux clarifications utilisateur (voir
> ci-dessous).

## Décisions architecturales

- **Respawn des pommes différé (CDC §5.2)** → l'`Environment` de la Phase 4
  respawnait *instantanément*. Décision utilisateur : passer à un respawn différé de
  `apple.respawn_delay = 150` ticks, via **3 patchs rétroactifs** minimaux (le reste
  des Phases 4/5 reste inchangé) :
  - `Apple.respawn_timer: int = 0` (compte à rebours hors-jeu).
  - `Environment._pending` (liste séparée — plus propre que des flags),
    `mark_eaten(apple)` (retire de `apples`, démarre le timer) et `tick_respawns(rng)`
    (décrémente, relocalise en zone safe et réintègre à 0).
  - `Agent.eat()` appelle `env.mark_eaten()` au lieu de `env.respawn()` (pommes
    collectées d'abord pour ne pas muter `apples` pendant l'itération).
- **`tick()` = unité atomique, pas de temps-réel ici** → la simulation n'importe ni
  ne touche Pygame (invariant n°7). `ticks_per_second` (cadence temps-réel) appartient
  au renderer Phase 7, qui appellera `tick()`. `run()` est le driver headless : il
  enchaîne les ticks sans `sleep`.
- **Pipeline par étages** (ordre validé par l'utilisateur, override du `6→7` de
  l'énoncé) : perception/action/repas → métabolisme/mort → respawn différé →
  reproduction → record/meilleur génome → compteur/CSV. Conséquence : un agent mort
  de vieillesse ne se reproduit pas ce tick-là (famine et seuil de repro sont
  mutuellement exclusifs côté énergie, donc seul ce cas diffère).
- **Compteur de pommes par agent côté Simulation** → `dict[Agent, int]` interne
  (`_apples_eaten`), alimenté par le retour de `eat()`. Évite de toucher `agent.py`
  pour le tracking ; le record et le meilleur génome en découlent directement.
- **Extinction propre** → `run()` s'arrête dès `population == 0` (`is_extinct`).
- **Déterminisme** → un seul `Random(simulation.seed)` partagé à l'`Environment` et à
  tous les agents ; `TRACKER.reset()` au démarrage pour des ids d'innovation stables.

## Implémentation

### Patchs rétroactifs
- `config/default.yaml` + `src/config.py` : `apple.respawn_delay` (validé `> 0`).
- `src/apple.py` : champ `respawn_timer: int = 0`.
- `src/environment.py` : `_pending`, `mark_eaten()`, `tick_respawns()`.
- `src/agent.py` : `eat()` → `mark_eaten()`.

### `src/simulation.py` (~250 lignes)

**`class Simulation`** — API :
| Membre | Contrat |
|---|---|
| `__init__(config, rng=None)` | `TRACKER.reset()`, crée `Environment`, spawn `population.initial_size` agents (génome fully-connected, position zone safe) |
| `tick()` | Avance d'un tick (pipeline par étages ci-dessus) |
| `run()` | Boucle headless jusqu'à extinction ou `simulation.max_ticks` (0 = infini) ; ouvre/ferme le CSV |
| `population_size` / `food_available` / `is_extinct` | Vues lecture seule |
| `tick_count` / `total_reproductions` / `record_apples` | Compteurs publics |

CSV (`CSV_HEADER`, 7 colonnes, une ligne tous les `logging.log_interval_ticks`) :
`tick, population, food_available, record_apples, avg_lifespan, total_reproductions,
avg_network_size`.
- `avg_lifespan` = moyenne de `agent.age` sur les vivants.
- `avg_network_size` = moyenne de `len(nodes) + nb_connexions_enabled` par génome.

Meilleur génome : `genome.to_json()` écrit dans `logging.best_genome_path` dès que le
record de pommes (lifetime) est battu.

### Tests — `tests/test_simulation.py` (11) + rétro (config 2, env 4, agent 1)

Init (taille pop, zone safe, déterminisme) · Tick (compteur, âges, métabolisme) ·
Repas + respawn différé via le pipeline · Record + meilleur génome rechargé ·
Reproduction (compteur + cap `max_size`) · Extinction (`run()` s'arrête) · CSV
(en-tête exacte, lignes, intervalle respecté).

## Patterns / Notes

- `tick()` reste appelable population vide : `tick_respawns` continue de ramener les
  pommes même après extinction (utile pour des tests d'environnement isolés).
- Recomposition de population : on retire les morts de `_apples_eaten` puis
  `population = vivants + enfants`, en une passe après la reproduction.
- Le cap `max_size` borne `survivants + enfants` à chaque tick (pas de surpopulation
  transitoire).
- Dette potentielle : `_update_record` scanne tout `_apples_eaten` à chaque tick
  (`O(pop)`) ; négligeable aux tailles visées. Le CSV est ré-écrit (`w`) à chaque
  `run()` — l'agrégation multi-runs sera l'affaire de la Phase 9 (AWS).

## Vérification

- `python -m pytest tests/test_simulation.py -v` → 11 verts.
- `python -m pytest tests/ -q` → 98 verts (non-régression Phases 1–5 incluse).
- `black src/ tests/` → formaté ; `pylint src/` → 10.00/10.
- Smoke headless 500 ticks : population 30→9, `food_available` variable (respawn
  différé actif), `record_apples` 2→4 avec `best_genome.json` écrit, 6 reproductions ;
  aucun import interdit (pygame/torch/tensorflow/neat).

## Hors périmètre (Phase 6)

- Rendu Pygame (agents, rayons, zone pénalité, HUD), mode headless via renderer
  non instancié, indicateur fin de vie → Phase 7.
- `main.py` (CLI argparse), smoke 500 ticks intégré, calibration → Phase 8.
- Upload S3 / DynamoDB / dashboard → Phase 9.
