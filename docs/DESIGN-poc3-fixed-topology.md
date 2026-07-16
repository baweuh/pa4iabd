# poc3 — Topologie de réseau fixe + forward pass batché ✅

## Contexte

Après la clôture du chantier HyperNEAT (poc2.5, V1-V4, tous falsifiés) et la
feuille de route recherche (5/5 items), constat de Robin : la quasi-totalité
des leviers testés jusqu'ici (fitness sharing, troncature, crossover, génome
sparse, critère minimal, îles, archive, biais, HyperNEAT) reposent sur la
sélection/reproduction — tous falsifiés. Les 4 leviers qui ont vraiment
marché (population 200→400, K-sweep, densité, novelty) sont tous liés à
l'**échelle**/l'**écologie**, jamais au mécanisme de sélection.

Recherche littérature (2026-07-16, non exhaustive mais convergente) :
Hamon, Nisioti & Moulin-Frier (2023, *Eco-evolutionary Dynamics of
Non-episodic Neuroevolution*) et Bejjani et al. (2025, *The Emergence of
Complex Behavior in Large-Scale Ecological Environments*) étudient
exactement le même paradigme que ce projet (non-épisodique, sélection
implicite par physiologie, pas de fitness explicite) et concluent que
certains comportements complexes **n'émergent qu'à grande échelle**
(population, environnement) — jamais observés en-deçà d'un seuil.

Verrou mesuré côté perf (audit poc2.4) : le forward pass NEAT hétérogène
était un plafond dur, non batchable tant que chaque agent a une topologie
différente. Et donnée clé : la population par défaut avait **<0,5 nœud
caché en moyenne après 30k ticks** — NEAT payait son coût plein (DFS
anti-cycle, tri topologique, spéciation par gènes d'innovation) pour une
évolution de topologie qui n'avait quasiment jamais lieu.

**But de poc3 (v1, ce chantier)** : remplacer le génome/réseau à topologie
variable par un réseau à topologie **fixe**, pour rendre le forward pass
batchable sur toute la population en un seul appel NumPy — préparer le
terrain pour tester l'hypothèse d'échelle (population ≫ 400) dans une
session future, sans encore la tester ici (scope volontairement borné à
une vérification mécanique, `hidden_size=0`, pop=400 identique à
aujourd'hui — isoler une seule variable, discipline constante du projet).

## Décisions architecturales

- **`Genome` devient un vecteur de poids plat + `layer_shapes` fixe**
  (`src/genome.py`), dérivé de `NetworkConfig` via
  `network_layer_shapes()` — jamais hardcodé (invariant n°1). `hidden_size:
  0` (défaut v1) = une seule couche linéaire `49→2`, la même capacité
  effective que le NEAT direct moyennait déjà (quasi 0 nœud caché). Le nom
  `Genome` est conservé pour minimiser le churn dans `agent.py`/
  `simulation.py`, même si sa nature interne a complètement changé.
- **Plus de mutation structurelle** : `add_node`/`add_connection`/
  `remove_node`/`remove_connection`/`InnovationTracker` disparaissent —
  une pile de couches en série ne peut pas former de cycle par
  construction, donc plus de vérification DFS (invariant n°3 réécrit).
  Seul le poids mute (`Genome.mutate`, perturbation gaussienne + clamp).
- **`src.network.batch_activate`** — le vrai livrable : empile les
  matrices de toute la population par couche (`(pop, in, out)`, garanti
  stackable puisque `layer_shapes` est identique pour tout le monde) et
  fait un `einsum` batché par couche, remplaçant la boucle Python
  `agent.decide()` par agent. `Agent.decide_from_raw()` (nouveau) applique
  la transformation égocentrique (tanh, heading) sur un résultat déjà
  calculé, sans réévaluer le réseau une seconde fois.
- **`src.speciation` simplifié** : sans topologie variable, plus de
  concept excess/disjoint (n'avait de sens qu'avec des ensembles de gènes
  différents alignés par innovation) — la distance dégénère à une moyenne
  de différence absolue sur le vecteur de poids partagé. Mécaniquement plus
  simple qu'avant, pas plus cher.
- **HyperNEAT supprimé, pas porté** (décision explicite de Robin :
  « on prend ce dont on a besoin de poc2 ») — bâti entièrement sur l'API
  NEAT structurelle, déjà falsifié (V1-V4), jamais promu. Historique
  complet préservé sur `poc2.5`/`poc2.6` (`docs/FALSIFIED-hyperneat.md`
  n'est pas touché). `src/hyperneat.py`, `tools/inspect_network.py`,
  `tools/trace_lineage.py`, `tests/test_hyperneat.py`,
  `config/lever_hyperneat_{mvp,v2,v3,v4}.yaml` supprimés.
- **Tout le reste réutilisé tel quel** : environnement, énergie,
  reproduction, capteurs, boucle de tick, renderer (panneau réseau adapté
  à la nouvelle forme, pas redessiné), novelty, K-sweep, densité — aucun
  changement de comportement écologique visé par ce chantier.

## Implémentation

- Fichiers réécrits : `src/genome.py` (~135 lignes), `src/network.py`
  (~95 lignes), `src/speciation.py` (~100 lignes, simplifié).
- Fichiers modifiés (touches ciblées) : `src/agent.py` (retrait branche
  HyperNEAT, nouveau `decide_from_raw`), `src/simulation.py` (`_spawn_agent`,
  `tick()` → `batch_activate`, colonnes CSV `avg_network_size`/
  `mean_hidden_nodes` désormais des constantes de config), `src/renderer.py`
  (`_draw_network_panel` réécrit sur `layer_shapes`/`matrices()`),
  `src/config.py` (`NetworkConfig.hidden_size`, `GenomeConfig`/
  `SpeciationConfig` allégés, `HyperNEATConfig` supprimé),
  `tools/steer_probe.py`, `tools/campaign.py`, `tools/run_and_probe.py`.
- Fichiers supprimés : voir liste HyperNEAT ci-dessus.
- Tests : `test_genome.py` (17, réécrit), `test_network.py` (10, réécrit —
  dont 3 verrouillent l'équivalence `batch_activate` vs boucle par-agent,
  linéaire ET avec couche cachée), `test_speciation.py` (14, réécrit),
  `test_agent.py`/`test_simulation.py`/`test_config.py` (fixtures
  adaptées). `test_hyperneat.py` supprimé. **238 tests verts**, black
  clean, pylint 9.99/10 (identique à avant, C0302 pré-existant sur
  `simulation.py` inchangé).

## Vérification

- Run réel headless (3000 ticks, seed 1) : aucun crash, population monte
  et tient à 400/400, nourriture disponible stable.
- **Équivalence numérique `batch_activate` vs boucle par-agent** :
  verrouillée par test dédié, tolérance `1e-10`, linéaire et avec couche
  cachée — condition de correction non négociable du chantier, tenue.
- **Mesure de perf** (pop=400, 3000 ticks, même machine, comparaison
  directe `poc2.6` vs `poc3` via `git worktree`) : **56,2 → 72,1 ticks/s
  (×1,28)**. Gain réel mais modeste — diagnostiqué par profil
  (`cProfile`, 500 ticks) plutôt que laissé tel quel :
  `batch_activate` ne représente plus que **2,8 % du tick** (contre "45 %,
  plafond dur" pour le forward pass NEAT hétérogène, audit poc2.4) — **le
  verrou visé est bien éliminé**. Le nouveau goulot dominant est
  `agent.eat()` (29 %, boucle Python `O(pop × pommes vivantes)` avec
  `math.hypot`, jamais batchée) et `batch_sense` (49 %, déjà optimisé en
  poc2.4 mais avec des conversions `.tolist()` résiduelles) — aucun des
  deux n'était dans le scope de ce chantier (« tout le reste réutilisé tel
  quel »). Le ×1,28 mesuré est donc le gain net compte tenu de ce nouveau
  plafond, pas un signe d'échec du levier — c'est la prochaine cible perf
  si on veut aller plus loin avant de monter en échelle.
- Sanity comportementale légère (2 seeds, 5000 ticks) : voir résultats
  dans le commit de clôture.

## Patterns / Notes

- Le nom `Genome` est trompeur si on ne lit pas ce document : ce n'est
  plus un graphe, c'est un vecteur de poids + une forme fixe. Gardé pour
  la continuité de l'API (`agent.reproduce()`, `simulation._spawn_agent`
  n'ont presque pas changé), documenté explicitement dans le docstring du
  module.
- `network_layer_shapes()` est le SEUL point de dérivation de forme —
  toute évolution future (`hidden_size` > 0, plusieurs couches) passe par
  cette fonction, jamais par un nombre en dur ailleurs.
- Les colonnes CSV `avg_network_size`/`mean_hidden_nodes` sont devenues
  des **constantes** (topologie fixe, jamais mutée structurellement) — plus
  des métriques émergentes comme sous NEAT. Gardées pour la stabilité du
  schéma CSV, pas parce qu'elles apportent encore de l'information.
- Non résolu dans ce chantier, dette connue et non bloquante :
  ~37 anciens fichiers `config/lever_*.yaml`/`config/apple_repro*.yaml`
  hérités de poc2.2-poc2.4 référencent encore les champs de mutation
  structurelle supprimés (`add_node_rate`, `c_excess`, etc.) et ne
  chargeraient plus sous poc3. Seuls les 3 fichiers activement utilisés
  par la suite de tests (`apple_repro_bigpop67.yaml`, `lever_novelty.yaml`,
  `lever_novelty_archive.yaml`) ont été corrigés — décision explicite de
  ne pas élargir le scope de ce chantier au nettoyage complet, hors du
  plan approuvé par Robin.

## Hors scope (sessions futures)

Sweep `hidden_size` > 0, GPU/JAX, re-validation complète des leviers
existants (novelty/K-sweep/densité) sous la nouvelle architecture à plus
grande échelle, nettoyage des configs legacy poc2.2-poc2.4, perf de
`batch_sense` (nouveau plafond dominant, voir addendum ci-dessous).

## Addendum — déblocage de l'échelle (même session, suite immédiate)

Avant de lancer une vraie campagne à grande échelle (le but même de
poc3), deux nouveaux murs perf identifiés en testant `population.max_size`
au-delà de 400 :

- **`agent.eat()` (29% du tick à pop=400, jamais batché)** : boucle Python
  O(pop × pommes vivantes). Remplacé par `src.agent.batch_eat` — une passe
  NumPy (matrice de distance agents×pommes) qui résout la compétition
  entre agents pour une même pomme **exactement** comme la boucle
  séquentielle (plus petit index gagne, puisque `eat()` ne lit jamais la
  position d'un autre agent). `Simulation.tick()` restructuré : décision +
  mouvement pour toute la population d'abord, puis un seul appel
  `batch_eat`. Équivalence verrouillée par `tests/test_batch_eat.py` (5
  tests, dont un sur un scénario contesté à la main et un sur un vrai run
  évolué à 50 ticks).
- **`population_novelty` (O(pop²), le levier novelty promu en défaut)** :
  un tenseur `(pop, pop, D)` de distances par paires — déjà 21% du tick à
  pop=2000, et une explosion mémoire pure (dizaines de Go) bien avant
  10 000 agents. Nouveau `novelty.max_pool_size` (0 = illimité/exact,
  défaut, **strictement inchangé** pour toute config existante) : au-delà
  de cette taille, un sous-échantillon aléatoire partagé (tiré via le RNG
  injecté, déterministe) tient lieu de pool complet — coût O(pop ×
  max_pool_size) au lieu de O(pop²), même trick que le k-NN de novelty
  search à grande échelle dans la littérature. Exclusion de soi-même
  toujours garantie même si l'agent tombe dans l'échantillon. 6 tests
  dédiés (`tests/test_novelty.py`), dont un qui vérifie l'exclusion de soi
  sur 20 graines différentes.

**Mesure (pop variable, `novelty.max_pool_size: 300`)** :

| max_size | ticks/s (avant ce correctif) | ticks/s (après) |
|---|:--:|:--:|
| 400 | 90,2 | 106,0 |
| 2000 | 23,9 | 32,8 |
| 4000 | 9,0 | 19,3 |
| 8000 | injouable (mémoire) | 12,3 |
| 16000 | injouable (mémoire) | 6,7 |

Profil à pop=8000 : `batch_sense` redevient le coût dominant (37,5%, linéaire
en pop — attendu, pas un mur comme les deux précédents) ; `population_novelty`
tombe à 10,8%. **249 tests verts, black clean, pylint 9.99/10.**

Une vraie campagne de recherche à grande échelle est maintenant
techniquement jouable (testé sans crash jusqu'à 16 000 agents) — reste à
décider avec Robin l'échelle cible et si `max_pool_size` doit être validé
comme approximation acceptable de novelty avant de s'y fier pour un
verdict de recherche.
