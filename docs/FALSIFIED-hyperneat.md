# HyperNEAT MVP (CPPN → substrat dense) — FALSIFIÉ, pire régression du projet (poc2.5)

> Chantier n°4 de la feuille de route recherche, dernier point ouvert. MVP
> dé-risqué implémenté, testé, câblé (`hyperneat.enabled`, off par défaut =
> legacy), puis évalué par campagne 6 seeds — comme tous les leviers
> précédents du projet. Détails d'implémentation :
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

## Décision

**Falsifié, non promu.** `default.yaml` garde `hyperneat.enabled` absent
(=false, legacy). Mécanisme gardé câblé + testé comme référence (267 tests,
`src/hyperneat.py`, `tools/inspect_network.py`, `tools/trace_lineage.py`).
Un substrat clairsemé (seuil LEO) ou un CPPN à connectivité fondatrice
partielle (`genome.initial_connectivity < 1.0`, déjà existant et falsifié
séparément pour l'encodage direct — poc2.3 volet 6, `docs/FALSIFIED` —
donc pas un candidat évident) sont les pistes de correction identifiées,
**non engagées** : ce chantier a atteint le niveau de rigueur (root cause
diagnostiquée, pas juste un score) où le projet arrête historiquement
d'itérer sur un mécanisme falsifié plutôt que de le retenter indéfiniment
sous une forme légèrement différente (cf. archive de nouveauté, un seul
essai après falsification du principal). Décision de retenter ou non une
V2 (substrat clairsemé) à discuter avec Robin, hors scope de cette session.

## Artefacts

- `src/hyperneat.py`, `src/geometry.py`, `HyperNEATConfig` (`src/config.py`)
- `src/agent.py` (`__init__`), `src/simulation.py` (`_spawn_agent`) —
  câblage conditionnel
- `src/network.py` — `activate()` généralisé à N sorties
- `tools/inspect_network.py`, `tools/trace_lineage.py`
- `tests/test_hyperneat.py`, extensions `tests/test_config.py`
- `config/lever_hyperneat_mvp.yaml`
- Campagnes : `logs/seed{42,7,123,1,5,99}/` (défaut et lever), 15k ticks
