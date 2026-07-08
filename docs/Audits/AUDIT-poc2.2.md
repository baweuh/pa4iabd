# Audit poc2.2 — état des invariants + correctifs ✅

Audit complet de la base poc2.1 (commit `7e3d32a`) contre les 7 invariants de
CLAUDE.md, suivi de quatre correctifs. Baseline avant correctifs : 114 tests
verts, pylint 10.00/10, black propre.

## Verdict invariants (poc2.1)

| # | Invariant | État |
|---|-----------|------|
| 1 | Zéro valeur hardcodée | ⚠️ respecté dans le code, mais 2 clés YAML mortes (voir fixes 1-2) |
| 2 | Énergie par tick | ✅ drain + pénalité appliqués par tick uniquement |
| 3 | Feedforward + DFS anti-cycle | ✅ `Genome._creates_cycle` (DFS), essai A→B puis B→A, abandon sinon |
| 4 | Topo sort calculé une fois | ✅ Kahn dans `NeuralNetwork.__init__`, construit dans `Agent.__init__` |
| 5 | Vitesse normalisée post-output | ✅ `clamp_velocity` (magnitude cappée, direction préservée) |
| 6 | Pommes en zone safe | ✅ inset `penalty_zone.width + apple.radius`, validé à la construction |
| 7 | Renderer séparé | ✅ aucun import Pygame hors `renderer.py`/`main.py` (lazy, visual only) |

## Correctifs appliqués

### Fix 1 — `sensors.fov` était une clé morte
`agent.sense()` et `renderer._draw_raycasts` codaient en dur `2π/num_rays` :
un YAML avec `fov: 180` était silencieusement ignoré. Nouveau helper public
`agent.ray_angles(num_rays, fov_degrees)`, partagé par la perception et
l'affichage (zéro dérive possible entre les deux). Avec `fov: 360`, les angles
sont bit-à-bit identiques à l'ancien code → déterminisme des runs préservé.

### Fix 2 — `logging.best_genome_path` était une clé morte
Validée, présente dans le YAML, jamais lue. Désormais `_save_best_genome`
écrit, en plus de l'archive `best_agents/agent_NNN_record_X.json`, le dernier
meilleur génome sous `logs/<run>/best_genome.json` (nom tiré de la config) —
un chemin stable pour récupérer le champion courant.

### Fix 3 — le renderer recalculait la perception
`_draw_raycasts` rappelait `agent.sense()` à chaque frame : coût de perception
doublé en mode visuel, et rayons affichés calculés *après* le déplacement (pas
ceux de la décision). `Agent.activate()` met maintenant en cache
`self.last_senses` (état public, lecture seule pour le renderer — invariant
n°7 intact). Le fallback `sense()` ne sert qu'aux agents jamais activés
(pause au tick 0, nouveau-nés).

### Fix 4 — la mise à l'échelle écran changeait la physique
`fit_window_to_screen` réduisait fenêtre + monde mais laissait zone pénalité,
rayons, vitesse et portée capteurs inchangés : sur petit écran, le mode visuel
simulait un monde *différent* du mode headless à YAML identique. Nouvelle
fonction pure `scale_spatial(config, scale)` : toutes les longueurs sont
multipliées par le même facteur, les énergies (par tick, invariant n°2) restent
intactes → le monde réduit est géométriquement similaire (mêmes entrées
normalisées, mêmes drains, même dynamique).

## Tests
- +6 tests : `ray_angles` (fov plein/réduit), cache `last_senses`,
  `best_genome.json` du run = dernier record archivé, `scale_spatial`
  (longueurs uniformes / énergies intactes).
- Suite complète verte, pylint 10.00/10, black propre.

## Points notés, non corrigés (volontairement)
- ✅ **Résolu 2026-07-08** (audit poc2.3, commit `928ccb7`) : `Agent.update()`
  duplique l'ordre des étapes de `Simulation.tick` (API de confort testée ;
  risque de dérive si l'ordre change un jour). *Le risque s'est confirmé —
  `update()` n'était plus appelé nulle part et divergeait déjà de `tick()`
  (ne comptait pas les pommes). Supprimé.*
- `TRACKER` global réinitialisé par `Simulation.__init__` : deux simulations
  simultanées dans le même process partageraient l'historique d'innovations.
- Un génome rechargé depuis JSON puis muté pourrait allouer des ids de nœuds
  en collision (le tracker ne connaît pas les ids chargés) — hors du flux
  actuel (les dumps servent à l'analyse, pas à la reprise).
- ✅ **Résolu 2026-07-08** (audit poc2.3, commit `9c56db2`) : `population.min_size`
  n'était pas appliqué — documenté comme choix (extinction réelle possible)
  dans `default.yaml`. *Confirmé vestigial (jamais lu par la logique) ; retiré
  du config et de la validation plutôt que branché.*
