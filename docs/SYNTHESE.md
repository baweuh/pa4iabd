# Synthèse du projet — ALife Neuroevolution

> Vue d'ensemble transverse : de la fondation technique (Phases 1-8) à la branche
> `poc2.3`. Pour le détail, voir `docs/Phase/*` (implémentation) et
> `docs/Audits/AUDIT-poc2.2-v3.md` + `AUDIT-poc2.3.md` (investigations).
> Rédigé le 2026-07-08, mis à jour le 2026-07-08 (volets 4-5 : crossover+bigpop
> falsifié, capteur 49 promu en défaut).

---

## 1. La trajectoire en un coup d'œil

```
Juin 10-12   Phases 1-8      Le simulateur (génome NEAT, réseau, agent, sim, rendu, CLI)
   ↓         poc2.1          Équilibrage énergie, calibration zone pénalité, logging/run
   ↓
Juil 6-7     poc2.2          INVESTIGATION : « pourquoi ça n'évolue pas ? » (ÉTAPES 0-10)
   ↓                         → Diagnostic + 1ère émergence robuste (apple_repro + bigpop)
   ↓
Juil 7-8     poc2.3          Capteurs 67 + viz réseau, puis 4 relances/audits :
                             volet 1 (perception) 🟡 · volet 2 (mutation) ❌ ·
                             volet 3 (crossover) 🟡 · volet 4 (crossover+bigpop) ❌ ·
                             volet 5 (ablation capteur → 49 promu défaut) ✅
```

Fil rouge unique de tout le projet **évolutif** : *le fourrage dirigé est trop
faiblement sélectionné pour être un attracteur stable* — sauf si on corrige le
**mécanisme** (couplage sélection↔compétence + faible dérive), jamais par simple
réglage de paramètre.

---

## 2. Fondations (Phases 1-8, juin) — le socle

Simulateur ALife **from scratch**, aucun framework ML (invariant projet), livré
phase par phase avec tests.

| Phase | Livré |
|-------|-------|
| 1 | `config.py` (dataclasses typées) + `default.yaml` — **zéro nombre magique** |
| 2 | Génome NEAT : `NodeGene`/`ConnectionGene`, 5 mutations, DFS anti-cycle, innovation counter |
| 3 | Réseau feedforward : tri topologique **caché à l'init**, forward pass |
| 4-5 | Environnement (pommes zone safe, zone pénalité gradient) + Agent (raycasts, énergie, cycle de vie) |
| 6 | Simulation : boucle fixed-timestep, population, extinction propre, CSV |
| 7-8 | Rendu Pygame **séparé de la logique** (invariant), CLI `main.py` (visual/headless) |

**Choix structurants** : réseau strictement feedforward ; sorties égocentriques
(`heading += output[1]×max_turn_rate`, `speed = output[0]×max_speed`) ; tout piloté
par YAML.

---

## 3. poc2.2 — l'investigation évolutive (le cœur)

**Question** : la population *survit* mais n'*apprend* rien à fourrager. Pourquoi ?

### Diagnostic (ÉTAPES 0-3) — enquête forensique
- **Preuve empirique** : après 24 000 ticks, le « champion » (record 27) est un
  **perceptron 49→2 nu**, aux poids quasi aléatoires, qui s'oriente *à l'opposé*
  des pommes (r = −0,17). **143 nouveau-nés aléatoires sur 200 font mieux.** Rien
  n'a été appris.
- **4 causes** :
  1. 🔴 Sélection sur le fourrage **minuscule** (survie quasi gratuite : 2 pommes/vie → mort de vieillesse)
  2. 🔴 Charge de mutation **détruit l'héritabilité** (80 % des poids re-randomisés/génération, RMS 1,77)
  3. 🔴 Complexification NEAT **jamais enclenchée** (fondateur déjà tout-connecté)
  4. 🟡 `mean_forage_rate` **bridé par l'offre** de nourriture (mauvaise métrique)
- **Instrumentation créée** : `tools/steer_probe.py` (sonde comportementale) +
  `tools/run_and_probe.py` (steering au niveau population) — **le vrai yardstick**.

### Campagne (ÉTAPES 5-9) — ~10 configs, ~30 runs, 3 seeds
> **Aucun réglage de paramètre ne rend le fourrage robuste sur les 3 seeds.**
> Chaque régime ne fait que **rebrasser quel seed gagne** (effet fondateur).
> L1 (mutation basse) + L2 (famine) = conditions *nécessaires*, aucune suffisante.

### Percée (ÉTAPE 10) — changement de **mécanisme**
`agent.apples_per_offspring` : fécondité ∝ **pommes cumulées** (pas énergie
instantanée). Couplé à la **grande population** (`apple_repro_bigpop.yaml`) :

| Config (30k) | seed 42 | seed 7 | seed 123 |
|--------------|---------|--------|----------|
| `apple_repro_bigpop` | 86 % | **84 %** | 56 % |

**1ère émergence robuste (3 seeds) ET stable (30k).** Seed 7 — bloqué 4-14 %
partout ailleurs — atteint 84 %. La repro apple-gated **ancre** le fourrage comme
attracteur (un non-fourrageur ne se reproduit jamais).

**Thèse validée** : blocage = **couplage sélection↔compétence faible** + **dérive
fondatrice**, à traiter *ensemble*, *structurellement*.

---

## 4. poc2.3 — capteurs, visualisation, cinq volets

### Volet 1 — Perception & instrumentation (livré ✅)
- **67 inputs** (au lieu de 49) : `apple_dist`/`wall_dist` séparés (4 canaux/rayon),
  **proprioception** (`actual_speed`), `apples_in_view`.
- **Panneau réseau (touche N)** : nœuds par groupe sensoriel, connexions par signe
  de poids → **évolution structurelle observable en direct**.
- Sparkline forage, HUD 3 lignes, fullscreen F11.

> ⚠️ **Changement de défaut** (commit `fa2656e`) : `apples_per_offspring` 0.0 → 5.0
> en même temps que les capteurs. Le défaut poc2.3 est donc « apple-gated repro **à
> petite population** » — la moitié seulement de la recette gagnante de poc2.2 (qui
> exigeait apple_repro **+ bigpop**). Documenté comme « état canonique » dans
> l'audit poc2.3 ; c'est la raison pour laquelle le contrôle fourrage mal.
>
> 🔴 **Réévalué au volet 5** : le capteur 67 lui-même s'avère **casser la
> robustesse** du package gagnant de poc2.2 (seed 123 : 43 %→1 %). Priorité
> performance oblige, il n'est plus le défaut — voir §4 volet 5.

### Volet 2 — Relance par **paramètre** (falsifiée ❌)
Hypothèse : `add_node_rate` 0,10→0,25 fera émerger des neurones cachés. Résultat à
30k : **0 caché chez les champions**, record figé à 53, dérive neutre (distance
génétique ×34, 51 espèces). **Amplifier la mutation quand sélection ≪ mutation ne
fait qu'accélérer la dérive.**

### Volet 3 — Relance par **mécanisme** = crossover (prometteur 🟢)
Crossover NEAT intra-espèce (piste (c) recommandée par le volet 2) :
- `Genome.crossover` : alignement par innovation, gènes matching aléatoires,
  disjoint/excess du parent apte, **enfant feedforward garanti** (invariant n°3).
- `genome.crossover_rate` (défaut 0.0 = legacy asexué) ; `config._build` rendu
  **rétro-compatible** (champs à défaut optionnels).
- `Simulation._pick_mate` : partenaire intra-espèce via `compatibility_distance` →
  **la spéciation devient une pression réelle** (elle n'était qu'observationnelle).

**Expérience — isolation à une variable, 30k. Campagne 3 seeds (% fourrageurs /
steering moyen population) :**

| Seed | Contrôle (xover OFF) | **Lever C (xover ON)** | Δ |
|------|----------------------|------------------------|---|
| 42   | 4 % / −0,284         | 88 % / +0,366          | +84 pts ✅ |
| 7    | 58 % / +0,123        | 96 % / +0,372          | +38 pts ✅ |
| 123  | 28 % / −0,086        | **10 % / −0,157**      | −18 pts ❌ |
| **moyenne** | 30 % / −0,082 | **65 % / +0,194**      | |

(Lever B / bigpop, seed 42 : 76 % / +0,232 — reconfirme le levier population.)

**Trois résultats :**
1. **Gros effet mais seed-dépendant.** À population identique, le crossover améliore
   fortement 2/3 seeds et fait passer la moyenne de anti-fourrage (−0,08) à fourrage
   (+0,19) — **mais régresse sur seed 123**. Il **n'atteint pas** le 3/3 positifs de
   `apple_repro_bigpop`. Le 22× de seed 42 était en partie de la chance de seed.
   **Non robuste au sens strict**, mais moyenne nettement meilleure.
2. **Les neurones cachés ne discriminent PAS** : présents (0,5–1,3 moy.) dans toutes
   les conditions, fourrageuses ou non. **Le signal est le comportement, pas la
   structure.**
3. **Convergence prématurée suspectée** sur seed 123 : le crossover verrouille
   peut-être plus vite le bassin fondateur (hypothèse non testée).

Sorties brutes : `logs/2026-07-08_crossover/` (6 runs, 3 seeds).

### Volet 4 — Crossover + bigpop, la piste (a) (falsifiée ❌)

Hypothèse : combiner recombinaison (volet 3) et anti-dérive par la population
(poc2.2) referait le 3/3 robuste. Config `lever_crossover_bigpop.yaml` (isolation
1 variable vs `lever_bigpop67`), 3 seeds / 30k :

| Seed | Crossover seul | Bigpop seul | **Crossover + bigpop** |
|------|:---:|:---:|:---:|
| 42   | 88 % | 76 % | **51 %** |
| 7    | 96 % | —    | **69 %** |
| 123  | 10 % | —    | **26 %** (steering encore négatif) |

**La combinaison sous-performe CHAQUE levier pris seul** (seed 42 : 76 %→51 %).
Le crossover **rapproche tous les seeds de ~50 %** — c'est un opérateur
**moyennant** (réduit la variance inter-seeds via mélange vers le comportement
moyen de la population), pas amplifiant. Explique d'un coup le sauvetage partiel
de 123 (volet 3) ET l'écrasement des gagnants. Conclusion : seule la **taille de
population** lève tous les seeds ensemble ; le crossover régularise, il n'élève pas.

### Volet 5 — Le capteur 67 casse la robustesse : retour au 49 (décisif ✅)

Priorité déclarée : **performance des agents**, quitte à revenir sur
l'enrichissement perceptif du volet 1. Le package physique robuste de poc2.2
(`apple_repro_bigpop`, 86/84/56 %) survit-il au capteur 67 ?

**Test décisif** : même package physique exact, seul `num_inputs` porté 49→67 →
seed 123 s'effondre **43 %→1 %** (steering −0,237). **Ablation** des 3 canaux
ajoutés (séparation apple/wall dist +16, proprioception +1, apples_in_view +1),
un par un, même package :

| Config | inputs | seed 42 | seed 123 |
|---|:---:|:---:|:---:|
| **49 (contrôle)** | 49 | **86 %** | **42 %** |
| split seul | 65 | 5 % | 89 % |
| proprio seul | 50 | 5 % | 39 % |
| apples_in_view seul | 50 | 32 % | 32 % |
| les 3 (67) | 67 | 59 % | **1 %** |

**Aucun canal isolé n'est coupable** — chacun dégrade déjà seed 42 tout seul ; ce
n'est pas *un* canal, c'est la **dimensionnalité d'entrée** (le génome part
toujours fully-connected, donc plus d'inputs = plus de connexions initiales à
régler = plus de surface de mutation = plus d'instabilité, peu importe le canal).

**Refonte technique** : le capteur devient **configurable**
(`sensors.split_distance/proprioception/apples_in_view`, tous `True` par défaut =
comportement 67 inchangé si omis) au lieu de câblé en dur — `SensorConfig.num_inputs`
dérive le compte (zéro nombre magique). `agent.sense()`, `tools/steer_probe.py`
(corrige un bug d'ambiguïté de layout : 50 inputs = proprio-seul OU aiv-seul) et
`src/renderer.py` généralisés en conséquence.

**Décision : `config/default.yaml` promu** au package `apple_repro_bigpop` complet
(monde ×√2, agents/pommes plus gros, mutation 0,15, `apples_per_offspring 3.0`,
pop 200/400) avec le **capteur 49**. 3/3 seeds confirmés à 15k (86/77/42 %,
cohérent avec l'étalon historique 98/86/43→86/84/56 à 30k, physiquement identique
— aucun nouveau run 30k nécessaire).

Sorties brutes : `logs/2026-07-08_bigpop67_screen/`, `logs/2026-07-08_arb67/`,
`logs/2026-07-08_ablation/`.

---

## 5. Où on en est / décisions ouvertes

- ✅ **`config/default.yaml` = package robuste 49-inputs, promu (volet 5).** Clôture
  la décision poc2.2 restée en suspens : monde ×√2, agents/pommes plus gros,
  mutation 0,15, `apples_per_offspring 3.0`, pop 200/400, capteur 49 legacy. 3/3
  seeds robustes (86/77/42 % à 15k).
- ❌ **Crossover (seul ou + bigpop) : non robuste, non promu.** `crossover_rate`
  reste à `0.0` dans le défaut — gain réel en moyenne côté crossover seul (30 %→65 %)
  mais rebrasse les seeds ; combiné à bigpop, sous-performe chaque levier seul (c'est
  un régularisateur de variance, pas un amplificateur).
- ❌ **Capteur 67 : non robuste, non promu par défaut.** Reste disponible via les
  toggles `sensors.*` (config, pas code) pour la viz/observabilité si besoin, mais
  casse le fourrage sur seed 123 — ne pas re-promouvoir sans nouvelle preuve.
- ❌ **Génome fondateur sparse (volet 6) : falsifié, plus lourdement que tout le
  reste.** `initial_connectivity 0.1` (~5 connexions/output au lieu de 49) devait
  réduire la surface de mutation identifiée au volet 5, mais dégrade **les 3 seeds
  sans exception** (86→6 %, 77→59 %, 42→7 % — la cible qu'on voulait sauver est
  le pire chiffre de toute la campagne). Le fully-connected agit comme filet de
  sécurité perceptif : le retirer laisse trop de capteurs débranchés trop
  longtemps. `initial_connectivity` reste à 1.0 dans le défaut.
- 🔑 **Enseignement transverse (volets 4 + 6)** : dans ce régime, tout mécanisme qui
  **réduit la richesse effective au démarrage** (crossover qui moyenne,
  connectivité qui prive d'information) nuit plutôt qu'il n'aide — même quand la
  théorie est solide. Seul un levier **additif** a marché dans tout le projet
  (plus de population, plus de sélection directe via `apples_per_offspring`).
- ⬜ **Piste ouverte** : seed 123 reste le maillon faible du trio (7-56 % selon le
  run, contre 59-98 % pour 42 et 7) — la suite doit être additive (N seeds /
  réglage de K / plus de population), pas une réduction de dimensionnalité.

---

## 6. État du code & qualité

- **155 tests verts**, `pylint` stable (9.94/10 — deux avertissements
  `too-many-locals`/`too-many-statements` pré-existants dans `renderer.py`, non
  liés aux volets 4-6), `black` clean.
- Invariants respectés : capteur piloté par config (zéro nombre magique, invariant
  n°1), feedforward garanti dans crossover, spéciation câblée dans le choix du
  partenaire, génome fondateur toujours ≥1 connexion/output (jamais de sortie
  muette même en sparse).
- Isolation expérimentale **rigoureuse** sur tout le projet : chaque levier = une
  seule variable modifiée depuis le contrôle (y compris l'ablation capteur du
  volet 5 canal par canal, et le dosage de connectivité du volet 6).

## 7. Historique des commits clés

| Commit | Objet |
|--------|-------|
| `009f2dc` | poc2.2 ÉTAPE 10 : repro ∝ pommes cumulées (1ère émergence robuste+stable) |
| `fa2656e` | poc2.3 : capteurs 67, proprioception, viz réseau (+ défaut apple_repro 5.0) |
| `804d3c5` | poc2.3 : audit clôture — relance par mutation falsifiée |
| `68305c2` | poc2.3 : crossover NEAT intra-espèce (Lever C) |
| `0b12070` | poc2.3 : audit volet 3 — le crossover débloque le fourrage (seed 42) |
| `4fb0892` | poc2.3 : volet 4 — crossover+bigpop (piste a) falsifiée |
| `7851137` | poc2.3 : volet 5 — capteur configurable, package 49-inputs promu en défaut |
| `807906d` | docs : synthèse à jour — volets 4-5 |
| *(à venir)* | poc2.3 : volet 6 — génome fondateur sparse, falsifié |
