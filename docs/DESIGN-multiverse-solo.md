# Multivers solo — 1 agent par cellule physiquement isolée (proposition, rien engagé)

> Chantier candidat poc2.6, proposé par Robin le 2026-07-16 pendant la
> campagne d'échelle poc3 (`config/lever_scale_4000.yaml`) : et si on
> lançait plein d'univers en parallèle avec un seul agent chacun ? Ce
> document est une proposition de design, **pas encore décidée ni codée** —
> à trancher avec Robin, au même titre que HyperNEAT V5 / repro non
> canonique / pistes hors sélection déjà listées dans `PLAN.md`.

## Motivation

La campagne pop=4000 (round 1) a régressé (moy foragers 72%→38%), mais le
résultat est confondu : 4000 agents pour 160 pommes, c'est ~5× plus dense
que le défaut — on ne sait pas si "plus d'agents" aide ou nuit, seulement
que "plus d'agents + bien moins de nourriture par tête" nuit. Le round 2
(`lever_scale_4000_scaled_food.yaml`, apples ×10) répare le ratio
pommes/agent mais garde les agents mélangés dans le même espace physique —
il reste un vrai signal de foule (positions qui se gênent, apples visées
par plusieurs agents à la fois) que la littérature motivant poc3 (Hamon
2023, Bejjani 2025) n'exclut pas d'invoquer comme ingrédient nécessaire.

Le multivers solo pose une question plus tranchée que les deux rounds
précédents : **est-ce que la sélection/reproduction implicite sur un grand
nombre d'individus suffit à faire émerger un comportement de fourrage
compétent, même quand aucun agent ne rencontre jamais un compétiteur** ?
Si oui → l'échelle aide par la **taille de l'échantillon évalué**
(beaucoup de variantes testées, la meilleure gagne des enfants), pas par
la dynamique écologique multi-agents. Si non (et que les rounds 1/2
régressent aussi) → l'interaction multi-agents elle-même (compétition,
peut-être même la simple présence d'autres agents comme signal sensoriel)
est un ingrédient nécessaire, pas un effet de bord.

## Leçon à ne PAS répéter : le modèle d'îles

`population.num_islands` (poc2.4, `docs/FALSIFIED-islands.md`) a déjà
testé une forme de fragmentation — mais il fragmentait le **pool de
reproduction/appariement** (chaque île = ses propres slots, son propre
classement de priorité, son propre pool de partenaires), pas l'espace
physique. Résultat : 4 îles de 100 agents rouvrent la dérive fondatrice
que poc2.2 avait corrigée en passant à pop 400 — chaque île isolée EST
fonctionnellement une petite population. **Les 6 seeds ont régressé.**

Le multivers solo doit fragmenter l'**espace physique** (qui rencontre
qui, qui mange quoi) **sans** fragmenter la sélection : le classement de
priorité pour la reproduction (`Simulation._priority_fn`,
`_reproduce_by_energy`/`_reproduce_by_foraging`), le pool de partenaires
(`_pick_mate`) et le calcul de nouveauté (`population_novelty`) doivent
rester **globaux, sur les N univers confondus** — sinon on retombe
exactement sur le réducteur déjà falsifié, avec un nom différent.

## Idée centrale

- Le monde est découpé en une grille de **cellules physiquement
  isolées** (murs internes, pas seulement le pourtour du monde). Chaque
  cellule contient **exactement 1 agent** à la fois (jamais 0 en régime
  stationnaire : à la mort, remplacement immédiat, comme aujourd'hui) et
  ses propres pommes (comptées et respawnées dans sa seule zone safe).
- `population.max_size` = nombre de cellules. Un agent ne voit jamais,
  ne mange jamais, n'entre jamais en compétition avec un agent d'une
  autre cellule — isolation écologique totale.
- **Ce qui reste global** (c'est le point central du design, voir section
  précédente) : qui se reproduit et avec qui (priorité + pool de
  partenaires), le score de nouveauté, la spéciation. Un agent excellent
  dans la cellule 12 peut avoir un enfant qui apparaît dans la cellule
  87 (celle qui vient de se libérer) — la sélection continue de comparer
  tout le monde entre eux, seule la vie quotidienne (manger, éviter les
  murs) est solo.

## Deux architectures possibles

### Option A — sharding spatial dans une seule `Simulation` (RECOMMANDÉ)

Une seule simulation, un seul monde, découpé en grille. Réutilise
`batch_sense`/`batch_eat`/`batch_activate`/`population_novelty`/
`_reproduce` quasi tels quels — ce sont déjà des opérations "population
entière en une passe NumPy", indifférentes à la géométrie tant que
chaque agent ne voit que ce qu'il doit voir.

**Changements de code réels nécessaires** (pas un simple fichier de
config comme les leviers précédents) :

1. **`Environment`/`Apple.spawn()`** (`src/environment.py`) : la zone
   safe est aujourd'hui calculée une fois pour tout le monde
   (`_x_max`/`_y_max` dans `Environment.__init__`). Il faut une zone safe
   **par cellule** — chaque pomme spawne à l'intérieur des bornes de sa
   cellule, jamais dans une autre.
2. **Bornes de déplacement de l'agent** (`src/agent.py`, `_clamp(...)`
   dans `move()` et `reproduce()`) : aujourd'hui bornées à
   `(0, world.width) × (0, world.height)`. Il faut border chaque agent
   dans sa **propre cellule** — sinon rien n'empêche physiquement un
   agent de traverser vers la cellule voisine, quel que soit ce que le
   raycast lui montre.
3. **Perception des murs** (`_raycast_batch`, `src/agent.py` lignes
   ~384-481) : le calcul de distance au mur utilise aujourd'hui
   `config.world.width/height` globaux. Il doit utiliser les bornes de
   la cellule de l'agent — sinon un agent perçoit le mur du MONDE au
   lieu du mur de SA cellule (incohérent avec le clamp du point 2).
4. **`Simulation._spawn_agent`/`_safe_spawn_position`** : aujourd'hui la
   position de naissance est tirée dans la zone safe globale. Il faut un
   mapping stable **slot ↔ cellule** (quel agent occupe quelle cellule) :
   quand un agent meurt en cellule 42, le remplaçant (choisi par
   priorité GLOBALE, cf. section précédente) doit apparaître DANS la
   cellule 42, pas n'importe où.
5. **Dimensionnement, à dériver de la config, jamais en dur** (invariant
   n°1) : `cell_width/height > 2 × sensors.max_distance` (aucun rayon ne
   doit pouvoir toucher la cellule voisine à travers le mur — trivial
   avec un vrai mur physique, mais la marge évite les rayons qui
   longeraient un mur commun). Nombre de cellules = `population.max_size`
   ; disposition (lignes × colonnes) à dériver d'un facteur proche du
   carré, pas hardcodée.

Ce qui ne change PAS : `_priority_fn`, `_reproduce_by_energy`/
`_reproduce_by_foraging`, `_pick_mate`, `population_novelty`,
`_refresh_novelty_scores`, la spéciation — tous continuent d'opérer sur
la liste complète des agents survivants, indépendamment de leur cellule.

### Option B — multivers au niveau process (mini-`Simulation` pop=1 par process)

Une variante façon `tools/campaign.py` (`ProcessPoolExecutor`), mais
avec `population.max_size=1` par process au lieu d'un seed complet.
Écartée pour un premier jet : ça oblige à **inventer un mécanisme de
sélection/reproduction inter-process** (aujourd'hui `_reproduce`/
`_pick_mate`/novelty lisent une liste Python d'`Agent` en mémoire, dans
un seul process) — il faudrait sérialiser les génomes/fitness entre
processes à intervalles réguliers, ce qui transforme le régime
**non-épisodique en temps réel** du projet (reproduction continue,
n'importe quel tick) en quelque chose de **générationnel par lots**
(un round de N ticks, on collecte, on sélectionne, on relance). C'est un
changement de paradigme plus profond que ce que ce chantier vise à
tester — à garder en réserve si l'option A s'avère elle-même limitée par
autre chose (ex. mémoire d'une grille énorme), pas un point de départ.

## Risques / inconnues à vérifier avant d'coder en dur

- **Confound résiduel possible** : avec N cellules et un nombre de
  pommes fixe par cellule, la variance de disponibilité de nourriture
  **par cellule** (petits nombres, ex. quelques pommes/cellule) peut
  elle-même devenir un facteur confondu si le nombre de pommes/cellule
  est trop petit — à vérifier empiriquement (comme pour le round 2),
  pas supposé.
- **Taille totale du monde** : N cellules × `cell_size` peut donner un
  monde très grand en absolu (ex. 4000 cellules ≈ un monde de plusieurs
  dizaines de milliers de pixels de côté). `batch_sense`/`batch_eat`
  sont censés rester bornés par le nombre de pommes/agents **visibles
  localement**, pas par la taille totale du monde — mais ce n'est vérifié
  nulle part pour une géométrie aussi étendue, à profiler avant toute
  campagne (même discipline que l'addendum poc3 : mesurer avant de
  conclure).
- **Un pas à la fois** : vérifier le mécanisme sur une petite grille
  (16-64 cellules, quelques milliers de ticks) avant toute campagne à
  grande échelle — même discipline que poc3 (`hidden_size=0` d'abord,
  pop=400 identique, PUIS scale).

## Statut

Proposition seule, rien engagé. Positionnée dans `PLAN.md` (branche
poc2.6) à côté de HyperNEAT V5 / repro non canonique / pistes hors
sélection — priorité et ordre à trancher avec Robin.
