# Audit poc2.3 — capteurs 67, visualisation réseau, et la relance de l'évolution structurelle

> Branche `poc2.3`. Trois volets : (1) un enrichissement **perceptif et
> instrumental** (67 inputs, proprioception, panneau réseau, sparkline forage,
> fullscreen) — livré et fonctionnel ; (2) une tentative de débloquer l'évolution
> structurelle par **réglage de paramètres** (`add_node_rate`) — **échouée**,
> confirmant le verdict poc2.2 v3 : *sur cette petite population, le système
> dérive, il ne s'adapte pas* ; (3) une relance par **mécanisme** (crossover NEAT
> intra-espèce) qui améliore fortement le fourrage sur 2/3 seeds (moyenne 30 %→65 %,
> steering −0,08→+0,19) mais **régresse sur seed 123** — **gain réel en moyenne,
> non robuste au sens strict** (pas de 3/3 positifs).

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
