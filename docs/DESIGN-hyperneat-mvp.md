# poc2.5 — HyperNEAT MVP (design + décisions)

> Chantier de recherche n°4 (dernier point ouvert de la feuille de route,
> voir memory `research-roadmap`) : tous les leviers "réducteurs" testés
> jusqu'ici (crossover, capteur 67, génome sparse, fitness sharing, biais,
> îles, critère minimal, troncature adoucie) sont falsifiés ; seuls les
> leviers additifs (novelty, K-sweep, densité) tiennent. HyperNEAT change de
> registre : ce n'est plus un réglage paramétrique mais un **changement de
> paradigme d'encodage**. Convenu avec Robin (2026-07-15) : commencer par un
> **MVP dé-risqué** avant la version complète. Cette session (1/N) livre la
> mécanique + l'outil d'itération rapide — pas encore la campagne de
> falsification (prochaine session).

## Idée

Au lieu que le génome NEAT décrive directement le réseau exécutable
(49→2), il décrit un **CPPN** (Compositional Pattern-Producing Network,
Stanley 2007) interrogé sur la géométrie du capteur pour produire les
poids d'un **substrat fixe**. Hypothèse : le capteur (anneau de 16 rayons)
a une régularité géométrique invisible à l'encodage direct (chaque poids
est appris indépendamment) — l'exploiter pourrait réconcilier richesse de
capteur et robustesse (le point qui a fait échouer le capteur 67 en
poc2.3 : ajouter des entrées élargit la surface de mutation initiale).

## Découverte clé : réutilisation totale de l'infrastructure NEAT

`Genome`/`NeuralNetwork` sont déjà génériques — ils ne savent rien de ce
qu'ils représentent. Un seul endroit crée le génome fondateur
(`Simulation._spawn_agent`), un seul endroit construit le réseau
exécutable d'un agent (`Agent.__init__`). Conséquence : le CPPN est un
génome NEAT ordinaire (mêmes opérateurs de mutation, même
`InnovationTracker`, même crossover, même distance de compatibilité) —
**zéro nouvelle machinerie évolutive**. `Agent.genome` devient le génome
du CPPN ; `Agent.network` reste un `NeuralNetwork` standard, mais dérivé
du CPPN à la construction au lieu d'être une lecture directe du génome
(invariant n°4 préservé : topo-sort une seule fois, à la naissance).

## Substrat (MVP simple)

- **Pas de couche cachée** : entrées → sorties directement, comme un
  génome fondateur `initial_connectivity=1.0`. Suffisant pour tester
  l'hypothèse centrale sans la complexité d'ES-HyperNEAT.
- **Coordonnées des entrées** (`src.hyperneat.substrate_input_coords`) :
  chaque entrée reçoit `(x, y, z)`. Les canaux "par rayon" (dist/
  apple_flag/wall_flag, ou leurs variantes séparées) sont placés sur le
  cercle unité à l'angle égocentrique du rayon (`src.geometry.ray_angles`,
  la même fonction que la perception réelle, extraite de `agent.py` dans
  ce chantier — voir "Refactor annexe" plus bas) ; `z` distingue le canal
  (une valeur par "genre" de canal, espacées uniformément dans `[-1, 1]`).
  Les entrées scalaires (énergie, proprioception, apples_in_view) sont au
  centre `(0, 0)` avec leur propre `z`. **Générique à tout `SensorConfig`**
  (testé sur les layouts 49 et 67), pas seulement le défaut.
- **Sorties** : 2 points fixes hors-anneau (`y = -1.5`), seulement pour
  être mutuellement distinguables — pas de géométrie propre (vitesse et
  virage ne sont pas des positions physiques).
- **CPPN** : 6 entrées (coordonnées des deux extrémités interrogées), 1
  sortie (poids brut). Activation `tanh` uniquement — pas de fonctions
  d'activation par nœud (sin/gaussienne) pour ce MVP.
- **Poids substrat** : `tanh(sortie_cppn) × hyperneat.weight_scale`
  (défaut 3.0) — borné, un seul paramètre neuf.
- **Densité** : substrat dense (chaque entrée connectée à chaque sortie),
  pas de seuil d'expression (LEO).

## Simplifications assumées (hors scope MVP, suivi possible si positif)

- Pas de couche cachée dans le substrat (ES-HyperNEAT).
- Pas de fonctions d'activation multiples par nœud CPPN (sin/gaussienne/
  sigmoïde) — seul `tanh` est utilisé, comme partout ailleurs dans le
  projet. Le cœur de l'hypothèse (corrélation géométrique des poids sur
  l'anneau) reste testable avec `tanh` seul : des coordonnées proches
  produisent des sorties de réseau proches, donc des poids substrat
  proches — la régularité n'exige pas la richesse d'activation complète
  d'un CPPN canonique, juste la continuité.
- Pas de seuil d'expression de lien (LEO / sparsification).
- Pas d'entrée de distance euclidienne au CPPN (augmentation classique).

## Refactor annexe : `src/geometry.py`

`ray_angles()` vivait dans `agent.py`. `src/hyperneat.py` en a besoin pour
les coordonnées substrat, mais `agent.py` importe aussi `hyperneat.py`
(pour construire le réseau substrat d'un agent) — import circulaire direct.
Extrait dans un module neutre `src/geometry.py` sans dépendance ; `agent.py`
importe désormais `ray_angles` depuis là (ré-exporté automatiquement, donc
`from src.agent import ray_angles` — utilisé par le renderer et les tests —
continue de fonctionner sans autre changement).

## Correctif annexe : `NeuralNetwork.activate()` généralisé à N sorties

`activate()` retournait un tuple codé en dur `(values[output_ids[0]],
values[output_ids[1]])` — jamais un problème tant que `network.num_outputs`
valait toujours 2 (invariant de config). Le CPPN a 1 seule sortie : la
methode a été généralisée à `tuple(values[nid] for nid in self.output_ids)`
— **rétrocompatible** (le cas 2-sorties produit exactement le même tuple),
couvert par la suite de tests existante inchangée.

## Sanity check (mécanisme, pas encore un verdict de recherche)

`tools/inspect_network.py` sur un génome CPPN issu d'un run court
(`config/lever_hyperneat_mvp.yaml`, 500 ticks, pop 30/40) :

```
CPPN: 7 nodes (0 hidden), 6/6 connections enabled
Substrate: 98 weights, mean -0.991  stdev 1.377  range [-2.812, +2.050]
steer_score: -0.899
geometric regularity: CPPN substrate 0.125  vs  200 random direct genomes 0.382 (±0.066)
resolution transfer (16 -> 32 rayons, PAS ré-évolué): steer_score -0.899 -> -0.876
```

Deux signaux encourageants pour le MÉCANISME (indépendants de la qualité
du comportement évolué, qui n'a pas encore été poussé) :
- **Régularité géométrique** : le substrat dérivé du CPPN est ~3× plus
  lisse d'un rayon à l'autre qu'un génome direct aléatoire — la
  corrélation géométrique visée existe bien, même avec `tanh` seul.
- **Transfert de résolution** : le même CPPN, réinterrogé à 32 rayons
  sans aucune ré-évolution, conserve un `steer_score` quasi identique —
  une capacité que l'encodage direct ne peut structurellement pas avoir
  (son nombre d'entrées est figé à la naissance).

## Hors scope de cette session

- `tools/trace_lineage.py` (2ᵉ outil convenu) — construit juste avant la
  campagne, à la session suivante.
- La campagne 6 seeds de falsification / décision de promotion.
- Les améliorations listées plus haut (couche cachée, multi-activation,
  LEO, entrée distance) si le MVP s'avère prometteur.

## Fichiers

- `src/geometry.py` (nouveau) — `ray_angles`, extrait de `agent.py`.
- `src/hyperneat.py` (nouveau) — coordonnées substrat, construction CPPN →
  substrat.
- `src/config.py` — `HyperNEATConfig` (section optionnelle, `enabled=False`
  par défaut).
- `src/simulation.py` (`_spawn_agent`), `src/agent.py` (`__init__`) —
  câblage conditionnel, zéro impact quand désactivé.
- `src/network.py` — `activate()` généralisé à N sorties.
- `config/lever_hyperneat_mvp.yaml` — lever isolant `hyperneat.enabled`.
- `tools/inspect_network.py` (nouveau) — boucle d'itération 0-tick.
- `tests/test_hyperneat.py` (nouveau, 15 tests) + extensions
  `tests/test_config.py` (3 tests) — 267 tests verts, black clean,
  pylint 9.98/10 (dette préexistante inchangée : `simulation.py`
  too-many-lines, `main()` sans docstring dans `tools/`).
