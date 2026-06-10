# Phase 5 — Agent (raycasts + énergie + cycle de vie) ✅

## Contexte

Phases 1–4 en place (`SimConfig`, `Genome`, `NeuralNetwork`, `Environment`).
Phase 5 introduit l'**Agent vivant** : il perçoit le monde via 16 raycasts
absolus, exécute son réseau, se déplace, métabolise son énergie *par tick*, mange
les pommes proches, se reproduit et meurt (famine / vieillesse). C'est le pont
entre la perception (`NeuralNetwork`) et le monde (`Environment`). L'orchestration
multi-agents (boucle de tick) appartient à la Phase 6 ; la Phase 5 livre l'unité
agent et ses tests.

> Aucun fichier CDC v5 n'est présent dans le repo : le design est piloté par les
> invariants CLAUDE.md et les conventions des modules existants.

## Décisions architecturales

- **L'agent possède son réseau** → `NeuralNetwork(genome, config.network)` est
  construit dans `__init__` et mis en cache. Honore l'invariant n°4 (tri
  topologique calculé UNE FOIS à la création, jamais recalculé). `activate()` ne
  prend donc pas de réseau en argument. *(Choix validé vs. la signature littérale
  `activate(network)` du prompt.)*
- **Raycasts absolus 360°** → rayon `i` à l'angle `i·(2π/num_rays)`, dans le
  repère monde. L'agent n'a pas d'orientation : pas d'état de cap à gérer, sense()
  pur et déterministe.
- **Zone pénalité implicite** → aucune entrée NN dédiée. L'agent ne perçoit la
  proximité murale que via les raycasts (type `1.0`) ; la pénalité agit sur
  l'énergie, pas sur les capteurs.
- **Premier-impact (first-hit)** → par rayon, on prend le plus proche entre la
  pomme la plus proche (intersection rayon-cercle) et le mur (intersection
  rayon-boîte). Rien dans la portée ⇒ distance `1.0`, type `0.0`.
- **Énergie enfant = `initial_energy`** → le parent paie `reproduction_cost`,
  l'enfant démarre à `initial_energy` (comme au bootstrap ; les pommes restent la
  vraie source d'énergie). *(Choix validé.)*
- **Position enfant = parent ± `radius`** → décalage tiré dans `±agent.radius`
  (paramètre config, pas de nombre magique), clampé dans le monde. Évite la
  superposition exacte sans introduire de nouveau paramètre.
- **`activate()` ne déplace pas** → renvoie la vitesse clampée ; `move()` est
  séparé pour garder l'ordre des étapes explicite côté Phase 6.

## Implémentation

### `src/agent.py` (~300 lignes)

**`class Agent`** — API :
| Méthode | Contrat |
|---|---|
| `__init__(genome, position, config, environment, rng)` | Construit le réseau (cache), `energy=initial_energy`, `age=0`, `alive=True` |
| `sense() → list[float]` | 33 entrées : `[0..15]` distances norm. `[0→1]`, `[16..31]` types `0.0/0.5/1.0`, `[32]` énergie norm. |
| `activate() → (vx, vy)` | Forward pass réseau caché + `clamp_velocity` (invariant n°5) |
| `move(vx, vy)` | Translation, clampée dans `[radius, W−radius]×[radius, H−radius]` |
| `metabolize()` | `−energy_drain_per_tick − penalty_at(x,y)`, cap `max_energy` (invariant n°2) |
| `eat() → int` | Mange chaque pomme à portée (`radius+apple.radius`), `+apple.energy` capé, respawn |
| `is_dead() → bool` | `energy ≤ 0` (famine) ou `age ≥ max_age` (vieillesse) |
| `can_reproduce() → bool` | `energy ≥ reproduction_threshold` |
| `reproduce() → Agent` | Paie le coût ; enfant = clone muté, `±radius`, `initial_energy` |
| `update()` | Helper 1 tick : age++, activate→move→eat→metabolize, MAJ `alive` |

Helpers géométriques purs (fonctions module) :
- `_ray_walls(px,py,dx,dy,W,H)` — plus petit `t>0` vers une paroi de la boîte
  (rayon unitaire ⇒ `t` = distance).
- `_ray_circle(px,py,dx,dy,cx,cy,r)` — racine positive la plus proche de
  `|P+t·D−C|²=r²` (a=1), `None` si raté ou cercle derrière.
- `_clamp`, `_closer`.

### `tests/test_agent.py` — 23 tests

Raycasts (mur droit devant, pomme sur l'axe, vide → 1.0/0.0, occlusion pomme<mur,
longueur 33, énergie normalisée) · Énergie (drain zone safe, drain+pénalité zone
murale, manger+respawn, double cap `max_energy`) · Mouvement (clamp mur) ·
Décision (vitesse clampée, déterminisme) · Cycle de vie (famine, vieillesse,
vivant, seuil reproduction) · Reproduction (coût payé, énergie/position/âge
enfant, agent & réseau indépendants) · `update()`.

## Patterns / Notes

- Les tests pilotent l'environnement en remplaçant `env.apples` (liste mutable)
  pour isoler la géométrie des raycasts — pas de hasard dans ces assertions.
- `sense()` est totalement déterministe (aucun `rng`) : le déterminisme du tick
  ne dépend que des poids du génome.
- Dette potentielle : `eat()` et `_cast_ray` itèrent toutes les pommes (`O(rays ×
  apples)`). Suffisant pour ~50 pommes ; une grille spatiale serait l'optimisation
  Phase 8 si besoin.
- `reproduce()` utilise le `TRACKER` global d'innovations (via `genome.mutate`),
  cohérent avec les Phases 2–3.

## Vérification

- `python -m pytest tests/test_agent.py -v` → 23 verts.
- `python -m pytest tests/ -q` → 81 verts (non-régression Phases 1–4).
- `black src/agent.py tests/test_agent.py` → formaté ; `pylint src/agent.py` → 10.00/10.
- Smoke : `sense` len 33, `|v| ≤ max_speed`, `metabolize` baisse l'énergie,
  enfant à `initial_energy`, `age=0`.

## Hors périmètre (Phase 5)

- Boucle de tick multi-agents, gestion de population, extinction → Phase 6.
- CSV logging, sauvegarde meilleur génome → Phase 6.
- Rendu agents/rayons → Phase 7.
