# HyperNEAT (CPPN → substrat) — FALSIFIÉ en V1 ET V2 (poc2.5)

> Chantier n°4 de la feuille de route recherche, dernier point ouvert.
> MVP dé-risqué implémenté, testé, câblé (`hyperneat.enabled`, off par
> défaut = legacy), évalué par campagne 6 seeds (V1) — pire régression du
> projet. Root cause diagnostiquée, corrigée, retesté (V2) — toujours
> falsifié mais amélioration mesurable (voir section V2 plus bas). Détails
> d'implémentation : `docs/DESIGN-hyperneat-mvp.md`.

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

## Décision

**Falsifié (V1 et V2), non promu.** `default.yaml` garde
`hyperneat.enabled` absent (=false, legacy). Mécanisme gardé câblé + testé
comme référence (273 tests, `src/hyperneat.py`, `tools/inspect_network.py`,
`tools/trace_lineage.py`). Deux itérations avec diagnostic root-cause à
chaque étape (pas juste un score) : la 1ʳᵉ correction (weight_scale) a
mesurablement amélioré la stabilité démographique mais laisse un écart de
compétence considérable. Poursuivre en V3 (ex. bootstrap de nœuds cachés
CPPN à la genèse, taux de mutation CPPN dédié plus élevé pour compenser le
couplage) est **une décision à prendre avec Robin**, pas automatique — le
gain V1→V2 (+4 points) est réel mais modeste au vu du coût d'une itération
complète (implémentation + campagne 6 seeds).

## Artefacts

- `src/hyperneat.py`, `src/geometry.py`, `HyperNEATConfig` (`src/config.py`,
  `weight_scale` + `connectivity`)
- `src/agent.py` (`__init__`), `src/simulation.py` (`_spawn_agent`) —
  câblage conditionnel
- `src/network.py` — `activate()` généralisé à N sorties
- `tools/inspect_network.py`, `tools/trace_lineage.py`
- `tests/test_hyperneat.py` (21 tests, dont 2 verrouillent le diagnostic
  empiriquement), extensions `tests/test_config.py`
- `config/lever_hyperneat_mvp.yaml` (V1), `config/lever_hyperneat_v2.yaml`
  (V2)
- Campagnes : `logs/seed{42,7,123,1,5,99}/` (défaut, V1, V2), 15k ticks
