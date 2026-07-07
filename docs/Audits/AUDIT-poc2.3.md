# Audit poc2.3 — capteurs 67, visualisation réseau, et la relance ratée de l'évolution structurelle

> Branche `poc2.3`. Deux volets : (1) un enrichissement **perceptif et
> instrumental** (67 inputs, proprioception, panneau réseau, sparkline forage,
> fullscreen) — livré et fonctionnel ; (2) une tentative de **débloquer
> l'évolution structurelle** (apparition/persistance de neurones cachés) par
> réglage de paramètres — **échouée**, et cet échec confirme une fois de plus le
> verdict de l'audit poc2.2 v3 : *sur cette petite population, le système dérive,
> il ne s'adapte pas.*

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
