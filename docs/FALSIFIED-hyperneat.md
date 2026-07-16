# HyperNEAT (CPPN → substrat) — FALSIFIÉ en V1, V2 ET V3 (poc2.5)

> Chantier n°4 de la feuille de route recherche, dernier point ouvert.
> MVP dé-risqué implémenté, testé, câblé (`hyperneat.enabled`, off par
> défaut = legacy), évalué par campagne 6 seeds (V1) — pire régression du
> projet. Root cause diagnostiquée, corrigée, retesté (V2) — toujours
> falsifié mais amélioration mesurable. V3 (bootstrap de nœuds cachés CPPN
> à la genèse) referme un gros morceau de l'écart (moy 19%→68% à 30k, vs
> 79% pour le défaut) mais reste **falsifié au sens strict** : un seed
> s'effondre (123 : 82%→12%). Détails d'implémentation :
> `docs/DESIGN-hyperneat-mvp.md`.

## Le mécanisme

`Agent.genome` devient un CPPN (6 coordonnées → 1 poids), évolué avec
l'infrastructure NEAT existante sans modification. `Agent.network` est
dérivé du CPPN à la construction : substrat FIXE, dense (chaque entrée
capteur connectée à chaque sortie), sans couche cachée — le poids de
chaque connexion vient de `tanh(cppn(coord_entrée, coord_sortie)) ×
weight_scale`. `hyperneat.enabled=false` (défaut) reproduit l'encodage
direct exactement, byte-à-byte (267 tests inchangés).

## Config testée

`config/lever_hyperneat_mvp.yaml` = défaut courant (novelty + densité +
K=1.5) + `hyperneat.enabled: true`, `weight_scale: 3.0` (aucun autre
paramètre touché — un seul levier isolé, comme toujours dans ce projet).

## Campagne 6 seeds/15k

| seed | 42 | 7 | 123 | 1 | 5 | 99 | **moy** |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| défaut 15k | 95 | 54 | 60 | 56 | 82 | 55 | **67** |
| HyperNEAT MVP 15k | 1 | 43 | 0 | 30 | 2 | 14 | **15** |
| Δ | **−94** | −11 | **−60** | −26 | **−80** | −41 | **−52** |

**Les 6 seeds régressent, aucune exception** — profil réducteur (comme
crossover, capteur 67, sparse init, fitness sharing, archive, biais, îles,
critère minimal), mais l'ampleur dépasse tout ce qui a été mesuré jusqu'ici
dans le projet (le pire précédent, le nœud de biais, était moy 62→28,
−34 ; ici moy 67→15, **−52**). `steer_median` passe **négatif** sur presque
tous les seeds (−0.07 à −0.72 : les agents pilotent en moyenne CONTRE les
pommes, pas seulement de façon neutre). Deux seeds s'effondrent
démographiquement : seed 123 termine à 190/400, seed 5 à 43/400 (quasi
extinction) — un symptôme jamais observé dans aucun levier précédent, même
les plus mauvais (îles, critère minimal) gardaient toujours pop=400.

## Diagnostic (root cause identifiée, pas juste un mauvais score)

Hypothèse initiale (mauvaise échelle des coordonnées de sortie fixes)
testée et écartée — la variance des poids substrat par rayon reste
substantielle (stdev moyen ~0,9) même quand le score s'effondre. La vraie
cause, vérifiée empiriquement :

```
Founder direct (100 génomes aléatoires) : steer_score == 0.0 exactement → 0/100
Founder CPPN→substrat (100 CPPN aléatoires) : steer_score == 0.0 exactement → 74/100
```

`steer_score` retourne exactement `0.0` quand la réponse de virage ne
varie PAS mesurablement selon quel rayon voit la pomme (garde
`dx*dy > 1e-12` dans `src.diagnostics.steer_score`, division par une
variance quasi nulle). Pour un génome direct, chaque connexion a un poids
tiré indépendamment — jamais dégénéré. Pour le substrat CPPN, les poids
des ~48 connexions entrantes d'une sortie (16 rayons × 3 canaux) sont tous
dérivés d'un même CPPN à 0 nœud caché (6 poids seulement) — fortement
corrélés entre eux par construction. La sonde `steer_score` ne fait varier
QU'UN SEUL rayon à la fois ; la contribution constante des ~47 autres
connexions (toutes actives, toutes pondérées) domine la somme et sature le
`tanh` de sortie **avant** que la variation d'un seul rayon ne puisse
déplacer la réponse — le signal utile est noyé dans un fond dense et
corrélé. C'est une conséquence directe de deux simplifications assumées du
MVP (`docs/DESIGN-hyperneat-mvp.md`) : **substrat dense** (pas de seuil
LEO/sparsification) + **CPPN sans nœud caché à la genèse** (`add_node_rate`
0,03/tick, campagne montre `hidden` moyen 0,10–0,45 après 15k ticks — la
topologie du CPPN n'a presque pas eu le temps de se complexifier). La
littérature HyperNEAT (D'Ambrosio & Stanley 2010, citée dans
`research-roadmap`) utilise justement un seuil d'expression de lien pour
cette raison précise — simplification que ce MVP avait délibérément
écartée pour rester "simple", et qui s'avère être la cause probable de
l'échec, pas un défaut du paradigme d'encodage indirect en général.

## V2 — correction ciblée, RE-FALSIFIÉ (amélioration réelle mais insuffisante)

Diagnostic affiné avant de relancer une campagne coûteuse (sweep
founder-level, 0 tick) : la sparsification seule
(`hyperneat.connectivity`, top-K poids par sortie) réduit la fraction de
fondateurs dégénérés mais ne la fait pas disparaître et ne redresse pas la
moyenne (74/100 → 26/100 à connectivité 0,1, moyenne toujours proche de 0
voire légèrement négative). La vraie cause dominante s'avère être
`weight_scale=3.0` : le CPPN (0 nœud caché à la genèse, donc purement
linéaire) sature son propre `tanh` de sortie **avant même** la sommation
du substrat — chaque poids individuel atterrit déjà près de ±3,0, quelle
que soit la paire (capteur, sortie) interrogée. Sweep : fondateurs
dégénérés 106/150 à `weight_scale=3.0` → **0/150 dès `weight_scale≤0,75`**,
avec une distribution `steer_score` alors comparable aux fondateurs à
encodage direct (moyenne proche de 0, dispersion saine, aucun zéro exact).

**Config testée** : `config/lever_hyperneat_v2.yaml` = défaut + une seule
variable changée vs le MVP falsifié — `hyperneat.weight_scale` 3,0→0,5
(`connectivity` laissée à 1,0/dense, mécanisme gardé mais pas combiné ici —
une variable à la fois).

**Campagne 6 seeds/15k :**

| seed | 42 | 7 | 123 | 1 | 5 | 99 | **moy** |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| défaut 15k | 95 | 54 | 60 | 56 | 82 | 55 | **67** |
| HyperNEAT V1 (dense, scale 3.0) | 1 | 43 | 0 | 30 | 2 | 14 | **15** |
| HyperNEAT V2 (dense, scale 0.5) | 0 | 6 | 0 | 37 | 22 | 50 | **19** |

**Toujours falsifié — les 6 seeds régressent encore, écart énorme (−48)** —
mais deux signaux d'amélioration réelle, pas cosmétique :
- **Plus aucun effondrement démographique** : les 6 seeds terminent à
  pop=400 (V1 avait 2 seeds proches de l'extinction, 190 et 43/400). La
  correction du diagnostic (saturation fondatrice) a bien éliminé ce
  symptôme précis.
- **+4 points de moyenne seulement** (15%→19%) — bien en-deçà de ce
  qu'annonçait le sanity check founder-level (dégénérescence éliminée à
  100%). Corriger la saturation des FONDATEURS ne suffit pas à rendre
  l'évolution compétitive sur 15k ticks : `hidden` moyen reste quasi nul
  (0,05–0,17, comme en V1) — le CPPN à 6 poids, fortement couplés entre
  eux (muter UN poids reroute simultanément les ~48 connexions du
  substrat), a très peu progressé structurellement. Hypothèse : le
  problème n'est plus la saturation fondatrice (corrigée) mais
  l'**évolvabilité** de cette paramétrisation à basse dimension — muter un
  seul des 6 poids CPPN a un effet global et fortement corrélé sur tout le
  substrat, un paysage de fitness beaucoup plus difficile à gravir par
  petites perturbations que les 98 poids indépendants de l'encodage
  direct.

## V3 — bootstrap de nœuds cachés CPPN, écart réduit mais RE-FALSIFIÉ (mixte)

Décidé avec Robin (2026-07-16) : des deux directions ouvertes par la
conclusion V2 (évolvabilité, pas saturation), tester le bootstrap de
nœud(s) caché(s) CPPN à la genèse — et lancer la campagne directement à
30k ticks (pas 15k puis re-validation), sur le précédent du levier
densité (`docs/RESULTS-density.md`) : négatif à 15k, positif à 30k, un
changement structurel lent à se manifester.

**Mécanisme** : le CPPN fondateur (0 nœud caché en V1/V2, donc purement
linéaire — chaque poids substrat est une simple combinaison des 6 poids
CPPN, fortement corrélés entre connexions) reçoit désormais N nœuds
cachés dès la naissance, en appelant `Genome.add_node` (le même opérateur
que la mutation en cours de vie utilise déjà — aucune machinerie
nouvelle : split NEAT classique, `in→new` poids 1.0, `new→out` hérite du
poids original) juste après `new_fully_connected`, avant même le premier
tick. Nouveau champ `hyperneat.bootstrap_hidden_nodes` (0 = legacy,
défaut). Câblage : `src/simulation.py::_spawn_agent`.

**Sweep fondateur (0 tick)** avant de lancer la campagne :
`tests/test_hyperneat.py::test_bootstrap_hidden_nodes_adds_nonlinearity_...`
confirme qu'ajouter 1 nœud caché sur V2 (déjà à 0 fondateur dégénéré) ne
réintroduit aucune dégénérescence — attendu, puisque le diagnostic V2
avait déjà établi que le problème n'était plus la saturation fondatrice
mais l'évolvabilité à long terme, invisible sur un snapshot à 0 tick.

**Config testée** : `config/lever_hyperneat_v3.yaml` = V2 (`weight_scale
0.5`, `connectivity` dense) + `hyperneat.bootstrap_hidden_nodes` 0→1
(une seule variable à la fois, comme toujours).

**Campagne 6 seeds/30k (défaut re-lancé frais pour comparaison directe) :**

| seed | 42 | 7 | 123 | 1 | 5 | 99 | **moy** |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| défaut 30k | 98 | 76 | 82 | 68 | 96 | 56 | **79** |
| HyperNEAT V2 15k (rappel, pas 30k) | 0 | 6 | 0 | 37 | 22 | 50 | **19** |
| HyperNEAT V3 30k (+1 nœud caché) | 97 | 63 | **12** | **92** | 50 | **91** | **68** |
| Δ (V3 vs défaut 30k) | −1 | −13 | **−70** | **+24** | −46 | **+35** | **−11** |

**Toujours falsifié au sens strict du projet (pas de campagne où les 6
seeds tiennent ou montent)** — mais un bond sans précédent dans ce
chantier, à la fois en direction et en magnitude :

- **`hidden` moyen passe de 0,05–0,17 (V1/V2) à 0,87–1,40** — le CPPN a
  réellement complexifié structurellement sur 30k ticks une fois parti
  d'une non-linéarité, confirmant le diagnostic V2 (le plafond était
  l'évolvabilité du CPPN à 6 poids purement linéaires, pas la saturation).
- **2 des 6 seeds dépassent nettement le défaut** : seed 1 (68→92, +24)
  et seed 99 (56→91, +35) — la première fois qu'un levier HyperNEAT bat
  le défaut sur un seed, et de loin.
- **2 seeds quasi stables** : 42 (98→97) et, dans une moindre mesure, 7
  (76→63).
- **2 seeds régressent lourdement** : 5 (96→50, −46) et surtout 123
  (82→12, −70, `steer_median` retombe à 0,000 — comportement de nouveau
  non directionnel, comme les pires cas V1). Le mécanisme n'élimine donc
  pas la fragilité fondatrice, il la déplace/réduit sa fréquence (1
  effondrement sur 6, contre systématique en V1/V2) sans la supprimer.
- **Moyenne toujours négative vs défaut** (79%→68%, −11), mais l'écart est
  descendu de −60 (V1) à −48 (V2) à **−11** (V3) — chaque itération avec
  diagnostic root-cause a réduit l'écart d'un facteur ~4-5, sans encore
  l'effacer.

Hypothèse pour un effondrement encore présent sur seed 123 : un seul nœud
caché ne garantit rien sur QUELLE connexion est splittée (`add_node`
choisit une connexion active au hasard) ni sur l'initialisation du poids
CPPN du nouveau nœud (tiré comme toute mutation de poids) — certains tirages
peuvent encore aboutir à un CPPN fondateur dont la non-linéarité ne
"décorrèle" pas suffisamment les ~48 connexions substrat pour ce seed
particulier. Non vérifié empiriquement (pas de sonde dédiée par seed) —
resterait à instrumenter si le chantier continue.

## Décision

**Falsifié (V1, V2 et V3), non promu.** `default.yaml` garde
`hyperneat.enabled` absent (=false, legacy). Mécanisme gardé câblé + testé
comme référence (278 tests, `src/hyperneat.py`, `tools/inspect_network.py`,
`tools/trace_lineage.py`). Trois itérations avec diagnostic root-cause à
chaque étape (pas juste un score) : V1→V2 (weight_scale) a corrigé la
saturation fondatrice et la stabilité démographique ; V2→V3 (bootstrap de
nœud caché) a comblé l'essentiel de l'écart de compétence restant
(−48→−11) et fait mieux que le défaut sur 2/6 seeds, mais laisse un seed
en échec sévère (123) — encore trop instable pour une promotion. Aller
plus loin (V4 : plus de nœuds bootstrappés, taux de mutation CPPN dédié,
ou diagnostic ciblé du cas 123) est **une décision à prendre avec Robin**,
pas automatique — le rythme de progrès (facteur ~4-5 par itération) reste
attractif, mais chaque itération coûte une campagne 6 seeds/30k complète
(~30 min machine).

## Artefacts

- `src/hyperneat.py`, `src/geometry.py`, `HyperNEATConfig` (`src/config.py`,
  `weight_scale` + `connectivity` + `bootstrap_hidden_nodes`)
- `src/agent.py` (`__init__`), `src/simulation.py` (`_spawn_agent`) —
  câblage conditionnel, y compris le bootstrap V3 (`add_node` × N à la
  genèse, avant le premier tick)
- `src/network.py` — `activate()` généralisé à N sorties
- `tools/inspect_network.py`, `tools/trace_lineage.py`
- `tests/test_hyperneat.py` (24 tests, dont 3 verrouillent le diagnostic
  empiriquement), extensions `tests/test_config.py`
- `config/lever_hyperneat_mvp.yaml` (V1), `config/lever_hyperneat_v2.yaml`
  (V2), `config/lever_hyperneat_v3.yaml` (V3)
- Campagnes : `logs/seed{42,7,123,1,5,99}/` (V1/V2, 15k) ; défaut + V3
  relancés frais à 30k pour cette comparaison (2026-07-16)
