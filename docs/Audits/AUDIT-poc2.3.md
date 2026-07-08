# Audit poc2.3 — capteurs 67, visualisation réseau, et la relance de l'évolution structurelle

> Branche `poc2.3`. Six volets : (1) un enrichissement **perceptif et
> instrumental** (67 inputs, proprioception, panneau réseau, sparkline forage,
> fullscreen) — livré et fonctionnel ; (2) une tentative de débloquer l'évolution
> structurelle par **réglage de paramètres** (`add_node_rate`) — **échouée**,
> confirmant le verdict poc2.2 v3 : *sur cette petite population, le système
> dérive, il ne s'adapte pas* ; (3) une relance par **mécanisme** (crossover NEAT
> intra-espèce) qui améliore fortement le fourrage sur 2/3 seeds (moyenne 30 %→65 %,
> steering −0,08→+0,19) mais **régresse sur seed 123** — **gain réel en moyenne,
> non robuste au sens strict** (pas de 3/3 positifs) ; (4) la piste (a) **crossover
> + bigpop** — **falsifiée** : la combinaison sous-performe *chaque levier pris
> seul* et rapproche tous les seeds de ~50 %. Le crossover est un opérateur
> **moyennant** (réduit la variance inter-seeds), pas amplifiant ; le seul levier
> qui *lève* tous les seeds ensemble reste la **taille de population** ; (5) **verdict
> final, priorité performance** : le capteur 67 inputs (volet 1) **casse la
> robustesse** (seed 123 : 43 %→1 %) — ni un canal précis ni la combinaison avec la
> population ne l'expliquent, c'est la **dimensionnalité d'entrée elle-même**
> (génome initial fully-connected plus large = plus de surface de mutation). Le
> capteur **49 legacy est promu en défaut** (`config/default.yaml`), via un nouveau
> layout de capteur **configurable** (`sensors.split_distance/proprioception/
> apples_in_view`, zéro nombre magique) plutôt qu'un revert de code ; (6) **génome
> fondateur sparse — falsifié**, et plus lourdement encore : démarrer avec
> `initial_connectivity 0.1` (~5 connexions/output au lieu de 49) devait réduire la
> surface de mutation identifiée au volet 5, mais **dégrade les 3 seeds sans
> exception** (86→6 %, 77→59 %, 42→7 %). La plupart des capteurs restent
> débranchés trop longtemps ; le fully-connected garantissait au moins un poids
> (même mauvais) sur chaque capteur dès la naissance — le sparse retire ce filet
> de sécurité sans le compenser à temps.

---

## Verdict en une phrase

Pousser `add_node_rate` de 0,10 à **0,25** (avec `apples_per_offspring` 5→3) sur
la population par défaut (100→200) ne fait apparaître **aucun neurone caché
persistant** : après 30 000 ticks le champion reste un **perceptron 67→2 nu**
(134 connexions, 0 caché), `record_apples` **plafonne à 53 dès le tick 10 000** et
n'augmente plus, pendant que la distance génétique **explose** (0,27 → 9,19) et le
nombre d'espèces monte à 51. Le taux de mutation structurelle amplifié ne produit
que de la **dérive neutre** : le seul levier qui avait débloqué le fourragement en
poc2.2 était la **taille de population** (`apple_repro_bigpop`, 200→400), pas le
taux de mutation.

---

## Volet 1 — Capteurs & instrumentation (livré ✅)

Commits `fa2656e` → `7605547`. Ce qui a été fait et fonctionne :

- **67 inputs** (au lieu de 49). `_cast_ray` sépare désormais `apple_dist` et
  `wall_dist` (4 canaux/rayon au lieu de 3) ; ajout de la **proprioception**
  (`actual_speed` = déplacement réel normalisé, 0 = bloqué) et de
  `apples_in_view` (fraction de rayons voyant une pomme). Layout complet dans
  `CLAUDE.md`. 143 tests passent.
- **Panneau réseau (touche N)** : nœuds colorés par groupe sensoriel, connexions
  colorées par signe de poids, alpha ∝ magnitude. Titre affiche `hidden:N` →
  diagnostic visuel immédiat de l'évolution structurelle.
- **Sparkline forage rate** (haut-droite), HUD 3 lignes (pommes/âge/convergence/
  vitesse réelle + Repro/Gen), **fullscreen F11** via `pygame.SCALED`.

Ces changements sont la vraie valeur de la branche : ils rendent l'évolution
structurelle **observable en direct** — ce qui a permis de constater tout de
suite que rien ne s'y passe.

---

## Volet 2 — Relance de l'évolution structurelle (échouée ❌)

### Hypothèse testée

Diagnostic préalable (commit `0ef9d38`) : sans crossover (lignée unique), une
innovation structurelle doit *survivre longtemps* pour se propager, donc on
augmente sa fréquence d'apparition et on interdit sa disparition :
`add_node_rate 0,10→0,25`, `remove_node_rate = 0,00`, `add_connection_rate 0,08`,
`apples_per_offspring 5→3` (plus de turnover). **Hypothèse : à 0,25, des neurones
cachés vont finir par s'établir dans les lignées sélectionnées.**

### Protocole

Run headless `logs/2026-07-07_142103`, seed 42, 30 000 ticks, `config/default.yaml`
avec les valeurs ci-dessus, population 100→200.

### Résultats (falsification de l'hypothèse)

| tick   | avg_network_size | record_apples | species | mean_genetic_distance | max_forage_rate |
|-------:|-----------------:|--------------:|--------:|----------------------:|----------------:|
| 100    | 203,00           | 2             | 1       | 0,27                  | 0,0200          |
| 2 000  | 203,43           | 17            | 5       | 1,19                  | 0,0364          |
| 10 000 | 204,35           | **53**        | 44      | 3,15                  | 0,0130          |
| 20 000 | 205,91           | 53            | 53      | 5,94                  | 0,0104          |
| 30 000 | 207,71           | 53            | 51      | **9,19**              | 0,0159          |

- **Champion final** = perceptron 67→2 nu : 67 inputs + 2 outputs, `max node id
  68`, **134 connexions toutes actives, 0 neurone caché**. Idem pour les **53
  best_agents** enregistrés : distribution des cachés = `{0: 53}`.
- `record_apples` **fige à 53 au tick 10 000** et ne bouge plus sur les 20 000
  ticks restants → aucune amélioration du fourragement.
- `max_forage_rate` ne monte pas (pic 0,036 tôt, puis ~0,015) → pas de tendance
  adaptative.
- `avg_network_size` croît lentement (+4,7 gènes) mais c'est de l'**accumulation
  de connexions**, pas de cachés persistants ; `mean_genetic_distance` × 34 et
  species → 51 = signature de **dérive neutre / diversification aléatoire**, pas
  de sélection convergente.

### Pourquoi ça échoue (et pourquoi c'était prévisible)

1. **Le fourragement ici est linéairement séparable « assez ».** Un perceptron
   67→2 suffit à s'orienter grossièrement ; un neurone caché ne confère aucun
   avantage de fitness détectable → il est purgé par dérive (les lignées qui en
   acquièrent un ne deviennent jamais record-holders, même avec
   `remove_node = 0`).
2. **Amplifier `add_node_rate` amplifie le bruit, pas le signal.** Avec une
   sélection déjà ≪ mutation (verdict poc2.2 v3), monter le taux de mutation
   structurelle ne fait qu'accélérer la dérive — visible dans l'explosion de la
   distance génétique et du nombre d'espèces.
3. **Le levier de poc2.2 n'était PAS le taux de mutation, c'était la population.**
   La seule émergence robuste + stable obtenue (audit poc2.2 v3, ÉTAPE 10) venait
   de `apple_repro_bigpop.yaml` : **population 200→400** + `apples_per_offspring
   3,0` + `add_node_rate 0,03` (bas !). Ce run poc2.3 a gardé la **petite
   population par défaut (max 200)** et a fait varier le mauvais bouton.

---

## Décisions de clôture

- **`config/default.yaml` remis à l'état canonique** (`add_node_rate 0,10`,
  `apples_per_offspring 5,0`) : l'expérience `0,25 / 3,0` est **falsifiée**, on ne
  la fige pas en défaut. Les valeurs testées + le résultat sont conservés ici et
  dans `logs/2026-07-07_142103/`. (Convention projet : les expériences vivent dans
  des configs nommées, `default.yaml` reste le monde de référence.)
- **Prochaine étape réelle = mécanisme, pas paramètre.** Si l'objectif est de voir
  émerger de la structure (neurones cachés utiles), il faut soit (a) une population
  large façon `apple_repro_bigpop` où la sélection domine la dérive, soit (b) une
  **tâche qui exige de la non-linéarité** (le fourragement actuel n'en exige pas),
  soit (c) introduire du **crossover / une pression de spéciation** pour que les
  innovations se recombinent au lieu de dériver isolément.

---

## Chiffres clés (vérifiés)

- Run : `logs/2026-07-07_142103`, seed 42, 30 000 ticks, pop 100→200.
- Config testée : `add_node_rate 0,25`, `remove_node_rate 0,00`,
  `add_connection_rate 0,08`, `apples_per_offspring 3,0`.
- Champion : 69 nœuds (67 in + 2 out), 134 connexions, **0 caché**.
- best_agents : 53 génomes, cachés = `{0: 53}`.
- `record_apples` : 53 (plateau depuis tick 10 000).
- `mean_genetic_distance` : 0,27 → 9,19. `species_count` : 1 → 51.

---

## Volet 3 — Le crossover débloque le fourrage (suite, seed 42) 🟢

Le volet 2 se terminait sur trois pistes « mécanisme, pas paramètre » : (a) grande
population, (b) tâche exigeant de la non-linéarité, (c) **crossover / pression de
spéciation**. Ce volet teste (c) — et (a) comme comparatif — contre un **contrôle
canonique** manquant jusqu'ici.

### Le mécanisme

Reproduction sexuée NEAT intra-espèce (commit `68305c2`). `Genome.crossover`
aligne les gènes par innovation : gènes *matching* tirés au hasard d'un parent,
*disjoint/excess* hérités du parent le plus apte (canonique). Enfant strictement
feedforward garanti (invariant n°3 : arête créant un cycle → skip). En simulation,
`Simulation._pick_mate` tire un partenaire et l'accepte s'il est sous le
`compatibility_threshold` de spéciation, avec probabilité `genome.crossover_rate`.
Nouvelle clé `genome.crossover_rate` (défaut `0.0` = clonage asexué legacy).

### Le protocole (3 runs, seed 42, 30 000 ticks)

Tous partent de la config **canonique** (`add_node_rate 0,10`,
`apples_per_offspring 5,0`) — contrairement au volet 2 à mutation poussée. Signal
mesuré : score de steering **au niveau population** (`tools.run_and_probe`), pas le
champion isolé (bruité sous turnover rapide).

| Run | Config | Pop | `crossover_rate` | Fourrageurs r>0.1 | Steer moyen | Cachés (moy / max) |
|-----|--------|-----|-----------------|-------------------|-------------|--------------------|
| **Contrôle** | `default.yaml` | 100→200 | 0.0 | **9/200 (4 %)** | **−0,284** | 0,83 / 3 |
| **Lever C** | `lever_crossover.yaml` | 100→200 | 0.6 | **177/200 (88 %)** | **+0,366** | 0,76 / 4 |
| **Lever B** | `lever_bigpop67.yaml` | 200→400 | 0.0 | 302/400 (76 %) | +0,232 | 0,52 / 4 |

### Deux enseignements

1. **Les neurones cachés ne sont PAS le discriminant.** Le contrôle en porte
   autant que les leviers (0,83 en **moyenne population**) tout en étant
   **anti-fourrageur** (4 %, steer −0,284). La structure cachée émerge dans les
   trois conditions à 30 000 ticks avec `add_node_rate 0,10` canonique. À
   rapprocher du « 0 caché » du volet 2, avec une précision de mesure importante :
   le volet 2 comptait les **champions** (`best_agents = {0: 53}`), ce volet compte
   la **population vivante entière** (`run_and_probe`). La lecture combinée est plus
   forte que « 0 caché » : la population *porte* des neurones cachés (0,5–0,8 en
   moyenne) qui **ne deviennent jamais record-holders** — ils ne confèrent donc
   aucun avantage de fitness détectable, exactement la Cause 3 de poc2.2 v3. **Le
   signal qui compte est le comportement (steering), pas le compte de neurones.**

2. **Le crossover a un gros effet à population constante — mais seed-dépendant.**
   À population *identique* (100→200), sur seed 42 activer le crossover fait passer
   le fourrage de 4 % à 88 % (facteur 22×) ; la recombinaison intra-espèce propage
   les innovations utiles au lieu de les laisser dériver isolément (mode d'échec
   diagnostiqué en poc2.2 v3). **Mais ce gain n'est pas uniforme sur les 3 seeds**
   (voir Statut) : le facteur 22× de seed 42 était en partie de la chance de seed.
   Lever B (population, 76 %) reconfirme séparément le levier de poc2.2.

### Statut : robustesse PARTIELLE — pas robuste au sens strict ⚠️

**Campagne 3 seeds livrée** (seeds 42, 7, 123 ; `{lever_crossover, default}` ;
30 000 ticks ; sorties dans `logs/2026-07-08_crossover/`). % fourrageurs (r>0.1) et
steering moyen population :

| Seed | Contrôle (xover OFF) | Lever C (xover ON) | Δ |
|------|----------------------|--------------------|---|
| 42   | 4 % / −0,284         | 88 % / +0,366      | **+84 pts** ✅ |
| 7    | 58 % / +0,123        | 96 % / +0,372      | **+38 pts** ✅ |
| 123  | 28 % / −0,086        | **10 % / −0,157**  | **−18 pts** ❌ |
| **moyenne** | 30 % / −0,082 | **65 % / +0,194**  | |

**Verdict.** Le crossover **améliore fortement 2/3 seeds** (42, 7) et fait passer la
moyenne population de anti-fourrage (−0,08) à fourrage (+0,19) — mais il **régresse
sur seed 123** (28 %→10 %). Il **n'atteint donc pas** le critère « 3/3 seeds
positifs » que `apple_repro_bigpop` avait réalisé en poc2.2 (86/84/56 %). Comme les
leviers paramétriques, le crossover **rebrasse partiellement quel seed gagne** — sa
moyenne est nettement meilleure, mais l'issue reste seed-dépendante.

**Hypothèse sur la régression seed 123** (non testée) : la recombinaison à mutation
haute accélère la convergence vers le bassin fondateur ; si les fondateurs de
seed 123 dérivent tôt vers l'anti-fourrage, le crossover *verrouille* ce bassin plus
vite (convergence prématurée — même risque que « mutation basse préserve la malchance
fondatrice », poc2.2 v3 ÉTAPE 5). À départager d'une éventuelle campagne élargie.

**Décision défaut :** `default.yaml` reste `crossover_rate 0.0`. Le crossover n'est
**pas** promu en défaut — gain réel en moyenne mais non robuste. Pistes suite :
(a) crossover **+ bigpop** (combiner recombinaison et anti-dérive, comme
apple_repro+bigpop l'a fait pour la sélection) ; (b) `crossover_rate` plus bas pour
limiter la convergence prématurée ; (c) accepter l'émergence contingente et rapporter
un taux de succès sur N seeds.

### Chiffres clés (vérifiés)

- 6 runs (2 configs × 3 seeds) + 1 run Lever B, 30 000 ticks. Sorties brutes dans
  `logs/2026-07-08_crossover/`.
- seed 42 — contrôle : 4 % / −0,284 ; Lever C : 88 % / +0,366 ; Lever B : 76 % / +0,232.
- seed 7 — contrôle : 58 % / +0,123 ; Lever C : 96 % / +0,372.
- seed 123 — contrôle : 28 % / −0,086 ; Lever C : 10 % / −0,157.
- Cachés (moyenne population) : 0,5–1,3 dans **toutes** les conditions, fourrageuses
  ou non → non discriminant (cf. enseignement 1).
- `record_apples` (45–60) reste borné par la longévité du champion
  (`max_age 5000`, respawn 150) — non discriminant ; le steering l'est.
- Qualité : 5 tests crossover, 148 tests verts, pylint 10/10, black clean.

## Volet 4 — Crossover + bigpop : la piste (a) falsifiée ❌

Le volet 3 laissait trois pistes. La plus prometteuse était (a) : combiner le
crossover (propage les innovations) **et** la grande population (anti-dérive, le
seul levier robuste de poc2.2). Hypothèse : comme `apple_repro + bigpop` avait
robustifié la *sélection*, `crossover + bigpop` robustifierait l'*adaptation*
jusqu'au 3/3.

### Le protocole

Config `config/lever_crossover_bigpop.yaml` = **isolation à une variable** vs
`lever_bigpop67.yaml` (pop 200/400) : seul `crossover_rate` passe 0.0→0.6. Trois
seeds (42, 7, 123), 30 000 ticks. Sorties dans `logs/2026-07-08_crossover_bigpop/`.

### Résultats

| Seed | Contrôle default | Crossover seul | Bigpop seul | **Crossover + bigpop** |
|------|:---:|:---:|:---:|:---:|
| 42   | 4 % / −0,284  | 88 % / +0,366 | 76 % / +0,232 | **51 % / +0,036** |
| 7    | 58 % / +0,123 | 96 % / +0,372 | —             | **69 % / +0,200** |
| 123  | 28 % / −0,086 | 10 % / −0,157 | —             | **26 % / −0,033** |

### Verdict : hypothèse (a) FALSIFIÉE

Ce n'est **pas** le 3/3 robuste espéré, et pire, la combinaison **sous-performe
chaque levier pris seul** :

- **Seed 42** : bigpop seul = 76 %, crossover seul = 88 % → **combinés = 51 %**.
  Ajouter le crossover au bigpop *dégrade* le meilleur seed.
- **Seed 7** : crossover seul 96 % → combiné **69 %**.
- **Seed 123** : crossover seul 10 % → combiné 26 %, mais steering encore
  **négatif** (−0,033, sous le hasard).

Aucun seed ne fourrage franchement ; un seed reste sous le random. Face à l'étalon
de robustesse (`apple_repro_bigpop` = 86/84/56, tous nettement positifs), échec net.

### L'enseignement : le crossover moyenne, il n'amplifie pas

Le fait décisif : le crossover **rapproche tous les seeds de ~50 %**. Il tire
seed 42 vers le bas (88→51), seed 7 vers le bas (96→69) et seed 123 vers le
haut (10→26). C'est le comportement d'un **opérateur moyennant** : la
recombinaison intra-espèce mélange les génomes vers le comportement *moyen* de la
population au lieu d'amplifier la meilleure lignée. Cela explique d'un seul
mécanisme **les deux effets** observés au volet 3 — le sauvetage de seed 123 ET
l'écrasement des gagnants. Le crossover **réduit la variance inter-seeds** : utile
contre une régression, néfaste pour capitaliser un succès.

Conclusion transverse (confirme poc2.2 et volet 3) : **seule la taille de
population lève tous les seeds ensemble.** Le crossover régularise, il n'élève pas.
Les pistes (b) `crossover_rate` plus bas et (c) taux de succès sur N seeds
resteraient dans le même régime « le crossover homogénéise » — elles ne
franchiront pas l'étalon `apple_repro_bigpop`, déjà notre meilleur résultat robuste.

### Chiffres clés (vérifiés)

- 3 runs (`lever_crossover_bigpop.yaml`, seeds 42/7/123, 30 000 ticks). Sorties
  brutes dans `logs/2026-07-08_crossover_bigpop/`.
- % fourrageurs (r>0.1) / steering moyen : 42 = 51 % / +0,036 ; 7 = 69 % / +0,200 ;
  123 = 26 % / −0,033. Pop pleine à 400 dans les 3 cas.
- Comparatif clé : sur seed 42, bigpop seul (76 %) > crossover+bigpop (51 %) →
  le crossover **soustrait** de la performance au bigpop.
- Cachés (moyenne pop) : 1,24–1,63 — toujours présents, toujours non discriminants.

## Volet 5 — Le capteur 67 casse la robustesse : retour au 49, capteur configurable ✅

Priorité déclarée : **performance des agents**, quitte à revenir sur l'enrichissement
perceptif du volet 1. Question fermée par ce volet : le package physique robuste
`apple_repro_bigpop` (86/84/56 %, poc2.2 ÉTAPE 10) survit-il au capteur 67 inputs ?

### Étape 1 — la population seule ne suffit pas (contredit l'hypothèse de départ)

`lever_bigpop67` (pop 200/400, capteur 67, reste identique à `default.yaml`),
3 seeds / 15k : **51 % / 88 % / 30 %**, seed 123 en steering négatif (−0,099). Ne
reproduit **pas** 86/84/56. `lever_bigpop67_lowmut` (+ mutation réduite 0,8→0,15) :
**33 % / 96 % / 22 %** — dégrade encore seed 42, ne sauve pas 123. Aucune des deux
hypothèses de la piste (b) ne comble l'écart : le facteur manquant n'est ni la seule
population, ni la seule mutation.

### Étape 2 — le package complet, porté au capteur 67, casse quand même

Config `apple_repro_bigpop67.yaml` = `apple_repro_bigpop.yaml` **isolation stricte** :
seul `num_inputs` passe 49→67 (le capteur 67 est câblé en dur dans `agent.sense()`
depuis le volet 1 — portage nécessaire). 3 seeds / 15k :

| Seed | Étalon (49) | arb67 (package complet, 67) |
|------|:---:|:---:|
| 42   | 98 % | 59 % / +0,098 |
| 7    | 86 % | 96 % / +0,367 |
| 123  | 43 % | **1 % / −0,237** 💥 |

Même package physique exact, seul le capteur change : seed 123 s'effondre
(43 %→1 %). **Le capteur 67 est bien la cause**, pas un artefact d'une combinaison
précédente.

### Étape 3 — ablation : aucun canal isolé n'est coupable, c'est la dimensionnalité

Le capteur configurable (`SensorConfig.split_distance/proprioception/apples_in_view`,
voir « Refonte technique » ci-dessous) permet d'isoler chacun des 3 canaux ajoutés
par le volet 1 (séparation apple/wall dist +16, proprioception +1, apples_in_view +1),
sur le même package physique, 3 seeds / 15k :

| Config | inputs | seed 42 | seed 7 | seed 123 |
|---|:---:|:---:|:---:|:---:|
| **arb49** (contrôle, tout off) | 49 | **86 %** / +0,352 | **77 %** / +0,125 | **42 %** / +0,118 |
| arb_split (séparation dist seule) | 65 | 5 % / −0,131 | — | 89 % / +0,220 |
| arb_prop (proprioception seule) | 50 | 5 % / −0,310 | — | 39 % / +0,070 |
| arb_aiv (apples_in_view seule) | 50 | 32 % / −0,035 | — | 32 % / +0,058 |
| arb67 (les 3 ensemble) | 67 | 59 % / +0,098 | 96 % / +0,367 | 1 % / −0,237 |

Aucun canal isolé ne reproduit la robustesse du 49 — chacun dégrade déjà fortement
seed 42 seul (86→5-32 %), et `arb_split` *sauve* seed 123 (89 %) tout en détruisant
seed 42 (5 %). **Il n'y a pas de coupable unique** : plus d'inputs signifie plus de
connexions initiales à régler dans le génome (toujours fully-connected à la
création), donc plus de surface de mutation et plus d'instabilité selon le seed —
peu importe la nature du canal ajouté. `mean hidden nodes` reste proche de 0
partout : ce sont des perceptrons nus qui divergent par le poids initial, pas par
la structure.

### Décision : capteur 49 promu en défaut

Vu la priorité performance, le capteur 49 legacy l'emporte nettement sur toutes les
variantes 67/allégées testées, sur les deux seeds discriminants (42, 123).
`config/default.yaml` est remplacé par le package `apple_repro_bigpop` complet
(monde ×√2, agents/pommes plus gros, mutation 0,15, `apples_per_offspring 3,0`,
population 200/400) avec le capteur 49. Confirmé 3/3 seeds à 15k (86/77/42 %,
cohérent avec l'étalon historique 98/86/43 → 86/84/56 à 30k, physiquement
identique). Aucun nouveau run 30k n'a été nécessaire : le package est
comportementalement identique à l'étalon poc2.2 déjà stabilisé sur 30k.

### Refonte technique : capteur configurable (zéro nombre magique)

`apple_repro_bigpop.yaml` utilisait `num_inputs: 49` en dur, incompatible avec
`agent.sense()` qui ne savait produire que 67 inputs depuis le volet 1 — le
promouvoir tel quel aurait crashé. Plutôt que de revert le code (perdant la
capacité à produire 67), le capteur devient **configurable** (invariant n°1) :

- `SensorConfig` gagne 3 toggles (`split_distance`, `proprioception`,
  `apples_in_view`, tous `True` par défaut = comportement 67 inchangé si non
  précisés) + une propriété `num_inputs` qui **dérive** le compte au lieu du
  nombre magique `4*num_rays+3`.
- `Agent.sense()` construit sa sortie en fonction des 3 toggles ; `split_distance`
  off → un seul canal de distance combinée (`min(apple_d, wall_d)`, équivalent au
  raycast legacy — les pommes ne peuvent pas être occluses par un mur car elles ne
  spawnent jamais au-delà, donc le combiné est fidèle).
- `SimConfig.__post_init__` valide `network.num_inputs == sensors.num_inputs`
  (dérivé) au lieu du calcul fixe.
- `tools/steer_probe.py` prenait le layout par la seule taille `num_inputs`, ce qui
  est **ambigu** (proprio seul et apples_in_view seul donnent tous deux 50) — corrigé
  pour reconstruire le vecteur de sonde à partir des 3 toggles réels, comme
  `agent.sense()`.
- `src/renderer.py::_draw_agent_rays` reconstruisait les rayons avec des indices
  4-blocs codés en dur — généralisé aux deux layouts (split/combiné).
- Tests : `test_sense_length_matches_configurable_layout` (4 layouts paramétrés,
  49/50/65/67), tests de rayons migrés sur une fixture `split_cfg` dédiée (le
  comportement split-distance reste testé même s'il n'est plus le défaut).
  **152 tests verts**, black clean, pylint stable (9.93/10, baseline pré-existante
  — deux `too-many-locals`/`too-many-statements` dans `renderer.py` antérieurs à
  ce volet, non introduits ici).

### Chiffres clés (vérifiés)

- 17 runs au total (screening 15k) : `lever_bigpop67`/`lowmut` ×3 seeds (6),
  `apple_repro_bigpop67` ×3 seeds (3), ablation `arb49/split/prop/aiv` ×2 seeds +
  `arb49` seed 7 (7), plus 1 smoketest. Sorties dans `logs/2026-07-08_bigpop67_screen/`,
  `logs/2026-07-08_arb67/`, `logs/2026-07-08_ablation/`.
- Configs conservées comme référence d'expérience : `lever_bigpop67(.yaml|_lowmut)`,
  `apple_repro_bigpop67.yaml`, `arb49/arb_split/arb_prop/arb_aiv.yaml`.
- `config/default.yaml` : monde 2263×1273, agent radius 11.31/speed 4.243, pommes
  160×radius 7.07, mutation 0.15/0.05, `apples_per_offspring 3.0`, pop 200/400,
  capteur 49 (3 toggles `false`). Tout `python main.py` désormais sur cette base.

## Volet 6 — Génome fondateur sparse : hypothèse falsifiée, plus lourdement encore ❌

Priorité toujours performance. Piste suivante identifiée pour remonter seed 123
(le maillon faible du package promu au volet 5, 42 % à 15k) : le volet 5 a montré
que la **connexité initiale** du génome (pas le nombre de capteurs) crée la
surface de mutation qui déstabilise le fourrage seed-dépendant. Hypothèse : un
génome **sparse** à la naissance (au lieu de fully-connected) devrait réduire
cette surface sans toucher aux capteurs — potentiellement compatible avec un
capteur riche (67) si l'effet se confirme.

### Refonte technique : `genome.initial_connectivity`

`GenomeConfig` gagne un champ `initial_connectivity: float = 1.0` (rétro-compatible,
`_require_rate`). `Genome.new_fully_connected` construit désormais, pour chaque
output, un sous-ensemble aléatoire d'inputs (`_founder_inputs_for`) au lieu du
bipartite complet — **au moins 1 connexion par output** (aucune sortie
définitivement muette), et à `connectivity == 1.0` **zéro tirage RNG
supplémentaire** : la séquence de poids est garantie identique au comportement
historique (test `test_full_connectivity_preserves_original_weight_draw_order`,
garde-fou contre une régression d'ordre de boucle attrapée pendant le
développement). 155 tests verts, black clean, pylint stable (9.94/10).

### Résultat expérimental : falsifié sur les 3 seeds sans exception

Config `lever_sparse_init.yaml` = `default.yaml` isolation 1 variable
(`initial_connectivity 1.0→0.1`, soit ~5 connexions/output au lieu de 49). 3 seeds
/ 15k, `logs/2026-07-08_sparse_init/` :

| Seed | Contrôle (fully-connected) | **Sparse init (0.1)** |
|------|:---:|:---:|
| 42   | 86 % | **6 %** 💥 |
| 7    | 77 % | **59 %** |
| 123  | 42 % | **7 %** 💥 (steering −0,373, le pire chiffre de toute la campagne poc2.3) |

Pas seulement non robuste : **dégrade tout, y compris la cible seed 123** qu'on
espérait sauver. Verdict sans appel, pas besoin de creuser d'autres valeurs de
`initial_connectivity` — le sens de l'effet est déjà contraire à l'hypothèse sur
tous les seeds.

### Pourquoi ça se retourne contre l'hypothèse

Avec `add_connection_rate` bas (0,05/génération) et ~5 connexions sur 49 capteurs
au départ, la plupart des inputs restent **complètement débranchés** pendant des
milliers de ticks — il faut une mutation structurelle rare pour rendre l'agent
« voyant » sur un capteur donné. Ce n'est pas « moins de poids à régler » comme
espéré, c'est « l'agent est aveugle sur l'essentiel de ses capteurs, et le
correctif est trop lent à arriver ». Le fully-connected garantissait au moins un
poids (même mauvais, même aléatoire) sur chaque capteur dès la naissance — un
filet de sécurité perceptif que le sparse retire sans le compenser à temps.

### Enseignement transverse

Troisième confirmation (après le crossover au volet 4, et maintenant le génome
sparse) que dans ce régime, les mécanismes qui **réduisent la richesse effective
au démarrage** (recombinaison qui moyenne, ou connectivité qui prive l'agent
d'information) tendent à nuire plutôt qu'aider — même quand la théorie
(dimensionnalité, variance) est solide. Le seul levier qui a marché dans toute
l'investigation poc2.2/poc2.3 reste **additif** : plus de population
(`apple_repro_bigpop`) ou plus de sélection directe
(`apples_per_offspring`), jamais une réduction de ce que l'agent perçoit ou
peut recombiner.

### Décision

`config/default.yaml` reste à `initial_connectivity 1.0` (implicite, champ non
défini). Aucune promotion. La config `lever_sparse_init.yaml` et le mécanisme
`initial_connectivity` sont conservés (code + config) comme référence
d'expérience et pour d'éventuels essais futurs à un dosage différent, mais rien
n'indique qu'un point intermédiaire inverserait la tendance observée sur les 3
seeds.

### Chiffres clés (vérifiés)

- 3 runs (`lever_sparse_init.yaml`, seeds 42/7/123, 15 000 ticks). Sorties brutes
  dans `logs/2026-07-08_sparse_init/`.
- % fourrageurs (r>0.1) / steering moyen : 42 = 6 % / −0,141 ; 7 = 59 % / +0,194 ;
  123 = 7 % / −0,373. Pop pleine à 400 dans les 3 cas.
- Pire résultat individuel de toute la campagne poc2.3 : seed 123 à −0,373
  (steering négatif le plus fort observé, plus bas que le volet 5 arb67 à −0,237).
