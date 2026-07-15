# Synthèse du projet — ALife Neuroevolution

> Vue d'ensemble transverse : de la fondation technique (Phases 1-8) à la branche
> `poc2.4`. Pour le détail, voir `docs/Phase/*` (implémentation), les audits
> `docs/Audits/*`, et pour poc2.4 `docs/DESIGN-poc2.4-perf.md` (perf) +
> `docs/RESULTS-novelty.md` (nouveauté).
> Rédigé le 2026-07-08, mis à jour le 2026-07-10 (poc2.4 : perf ×4 de la boucle
> de recherche, et bonus de nouveauté = 1er levier positif, promu en défaut).

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
   ↓
Juil 10      poc2.4          Perf ×4 de la boucle de recherche (campagnes parallèles
                             + perception batchée NumPy), puis reprise recherche :
                             bonus de NOUVEAUTÉ ✅ = 1er levier positif (+10 sur
                             6 seeds), promu en défaut (52 %→62 % fourrageurs)
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
- ✅ **Bonus de nouveauté additif = 1er levier POSITIF (poc2.4), promu en défaut.**
  Novelty search (Lehman & Stanley 2011) câblé comme **bonus additif** sur la
  priorité de repro. Campagne 6 seeds/15k : moy **52 %→62 % (+10)**, **chaque seed
  monte ou tient, aucun ne régresse** — l'inverse exact des réducteurs. Sweep de
  `weight` → optimum franc à 1.0 ; `recompute_interval=10` efface le coût O(pop²)
  au débit de base. `default.yaml` l'active (meilleur défaut jamais atteint).
  Détails : `docs/RESULTS-novelty.md`.
- 🔑 **Enseignement transverse confirmé** : dans ce régime, tout mécanisme
  **réducteur** (crossover qui moyenne, capteur 67, sparse, fitness sharing —
  4 falsifications) nuit ; seuls les leviers **additifs** marchent (population,
  sélection directe `apples_per_offspring`, et désormais **bonus de nouveauté**).
  La nouveauté est la 1ʳᵉ validation *positive* et prédictive de ce pattern.
- ⬜ **Piste ouverte** : seed 123 et les seeds durs (1, 99) restent bas en absolu
  (20-27 %) malgré la nouveauté — aidés, pas « résolus ». Suite additive possible :
  **archive de nouveauté** (comportements passés, pas seulement la pop courante).
- ⬜ **À rectifier — durée de vie des pommes trop courte (observé en jeu,
  2026-07-09, Robin)** : à population proche du plafond (`max_size: 400`) sur la
  carte 2263×1273 avec 160 pommes, les pommes semblent mangées quasi
  instantanément (~1,5 s), probablement par des trajectoires d'agents non
  dirigées plutôt que par du fourrage skillé — la carte est surpeuplée relatif à
  l'offre. Risque : dilue le signal de sélection que `apples_per_offspring` est
  censé fournir (manger devient fortuite plutôt que discriminant). Lié à la
  cause #1 du diagnostic poc2.2 (« sélection sur le fourrage minuscule ») mais
  sous l'angle inverse (trop de densité agents/pommes plutôt que pas assez de
  pression). À investiguer avant tout nouveau levier de sélection (fitness
  sharing y compris) : instrumenter la durée de vie moyenne des pommes et/ou
  distinguer captures dirigées (steering positif juste avant capture) vs
  fortuites — sinon le signal qu'on cherche à amplifier (fitness sharing) est
  peut-être déjà noyé en amont.

  **Vérifié 2026-07-09** (`tools/apple_capture_probe.py`, pop pleine 400/400,
  2 seeds) : confirmé, et pire que l'estimation visuelle — durée de vie
  médiane **0,20-0,27 s** (pas 1,5 s), seulement **7-11 %** des 160 pommes
  vivantes à tout instant (file de respawn saturée). Classification par
  capture (adjacent = agent déjà sur place à l'apparition ; directed =
  approche mesurée nette ; undirected = ni l'un ni l'autre) :

  | Seed | adjacent | directed | undirected | lifetime médiane |
  |---|---|---|---|---|
  | 42  | 23 % | 48 % | 29 % | 12 ticks (0,20 s) |
  | 123 | 25 % | 44 % | 31 % | 16 ticks (0,27 s) |

  **52-56 % des captures ne montrent pas d'approche dirigée nette**, cohérent
  sur les deux seeds testés. Confirme qu'il faut traiter ce goulot AVANT
  d'amplifier la sélection (le fitness sharing amplifierait un signal déjà à
  moitié bruité). Piste additive préférée (cohérente avec le pattern
  transverse) : augmenter l'offre de pommes (`apple.count` et/ou
  `respawn_delay` plus court) ou agrandir la carte, plutôt que réduire
  `population.max_size` (réducteur — pattern qui a toujours cassé la
  robustesse ailleurs dans le projet).

  **Testé 2026-07-09** : levier « agrandir la carte » (choix de Robin),
  `config/lever_bigmap.yaml` (world ×√2, 2263×1273→3200×1800, tout le reste
  isolé/inchangé). Effet de bord observé pendant le test : la carte plus
  grande **ralentit encore la sim** (moins de pommes mangées vite → plus de
  pommes vivantes simultanément → raycast plus cher) — même mécanisme de coût
  que les leviers apple.count/respawn_delay écartés plus haut ; a motivé la
  priorité NumPy ci-dessous.

  Résultat (seed 42, 4000 ticks vs contrôle 8000 ticks — run réduit pour
  tenir dans le budget) :

  | | contrôle (2263×1273) | bigmap (3200×1800) |
  |---|---|---|
  | food vivant | 11/160 | 38/160 |
  | lifetime médiane | 12 ticks (0,20s) | 27,5 ticks (0,66s) |
  | adjacent | 23% | **12%** |
  | directed | 48% | **63%** |
  | undirected | 29% | 25% |

  Progrès net sur les 3 axes (moins de gratuit, plus de dirigé, pommes qui
  durent 2× plus longtemps). **Pas encore validé au niveau évolutif** : un
  seul seed, run court, mesure la composition des captures pas le %
  fourrageurs — avant promotion en défaut, refaire la campagne complète
  (3 seeds/15-30k ticks, `tools/run_and_probe.py`) comme pour chaque levier
  précédent du projet. Mis en pause au profit du chantier NumPy (perf
  bloquante pour ces campagnes) puis du fitness sharing (ordre convenu avec
  Robin).

- ✅ **Fait — raycast vectorisé NumPy + cache pommes** (2026-07-09, suite au
  test bigmap). `CLAUDE.md` liste déjà NumPy dans le stack autorisé
  (l'interdiction ne vise que les frameworks ML : neat-python/torch/tensorflow/
  gym) ; le code ne l'utilisait nulle part avant cette session. Deux étapes :
  1. `agent._cast_ray` (boucle Python par rayon×pomme) → `_cast_rays` +
     `_ray_walls_vec`/`_ray_circles_vec` (`src/agent.py`), calcul batché en
     array NumPy pour un agent. Seul, ce changement n'a donné que **+7%**
     (14,44→15,46 ticks/s) : l'overhead fixe NumPy par appel mange presque
     tout le gain à ces tailles de tableau (16 rayons × ~11-38 pommes vivantes).
  2. Vrai goulot identifié en creusant : `agent.sense()` reconstruisait les
     tableaux NumPy des positions de pommes **à partir de la liste Python à
     chaque agent** (400×/tick) alors que la liste ne change que ~1-2×/tick.
     Fix : `Environment.live_apple_coords()` (`src/environment.py`), cache
     invalidé uniquement par `mark_eaten`/`tick_respawns`. **+25% au total**
     (14,44→18,04 ticks/s), zéro changement de comportement (même ordre
     séquentiel agent par agent, même détermisme).
  **Piste écartée délibérément** : batcher toute la population en un seul
  appel NumPy (tableau pop×rayons×pommes) irait sans doute plus vite mais
  **change la sémantique** — aujourd'hui un agent traité après un autre dans
  le même tick ne voit plus une pomme que ce dernier vient de manger
  (perception séquentielle) ; batcher toute la population calculerait les
  perceptions AVANT que quiconque ait mangé ce tick, ce qui change le
  comportement émergent et invaliderait silencieusement les campagnes de
  robustesse déjà validées (86/84/56 etc.) sans revalidation. Décision prise
  avec Robin : ne pas le faire, le +25% sans risque suffit pour l'instant.
  Ne PAS utiliser torch/tensorflow pour le NN : le forward pass n'est pas le
  goulot, ce projet ne calcule jamais de gradient (poids évolués par mutation
  NEAT, pas par backprop), et chaque agent a une topologie différente
  (mauvais fit pour du calcul batché à architecture fixe). 148 tests verts,
  pylint 10/10, black clean.

---

## 6. État du code & qualité

- **148 tests verts**, `pylint` stable (9.93/10 — deux avertissements
  `too-many-locals`/`too-many-statements` pré-existants dans `renderer.py`, non
  liés aux volets 4-6), `black` clean.
- Invariants respectés : capteur piloté par config (zéro nombre magique, invariant
  n°1), feedforward garanti dans crossover, spéciation câblée dans le choix du
  partenaire, génome fondateur toujours ≥1 connexion/output (jamais de sortie
  muette même en sparse).
- Isolation expérimentale **rigoureuse** sur tout le projet : chaque levier = une
  seule variable modifiée depuis le contrôle (y compris l'ablation capteur du
  volet 5 canal par canal, et le dosage de connectivité du volet 6).

### Audit + nettoyage (2026-07-08)

Relecture code complète + recherche littérature (NEAT/novelty/HyperNEAT). Trois
nettoyages livrés :
- **Code mort supprimé** : `clamp_velocity` (la vitesse est bornée par
  `tanh×max_speed`, le clamp ne servait plus), `Agent.update()` (jamais appelé —
  `simulation.tick()` ré-inline le pipeline), `Environment.respawn()` (redondant
  avec `tick_respawns`). 7 tests morts retirés (155→148).
- **`population.min_size` retiré** : jamais branché sur la logique runtime (un
  plancher contredirait l'intent ALife : l'extinction est légitime). Enlevé des
  23 configs + validation.
- **`CLAUDE.md` corrigé** (spec ↔ code : « Inputs NN : 67 » → capteur configurable
  défaut 49 ; commande `--mode headless`). *Non versionné (gitignoré).*

**Prochain chantier identifié** : brancher le **fitness sharing NEAT** — la seule
vraie tuyauterie calculée (`speciation.py`) mais jamais reliée à la sélection.
Pattern des échecs volets 4/5/6 : les leviers *réducteurs* (crossover, +inputs,
sparse) cassent ; seuls les *additifs* (population, sélection directe) marchent.

### Audit de tuyauterie fonctionnelle (2026-07-09)

Enquête « est-ce que tout est connecté, fonctionnel et *utilisé* ? », centrée
agents — détail dans `docs/Audits/AUDIT-poc2.3-tuyauterie.md`. **Verdict** : la
boucle de vie de l'agent est pleinement connectée et fonctionne (vérifié par run
instrumentée : nourriture 160→24, record→15, repro→231, maxgen→5 en 1250 ticks).
Mais une part notable du code est **câblée + testée + jamais empruntée** par
`default.yaml` : chemin de repro par énergie, crossover (donc `compatibility_distance`
côté sélection), capteurs riches (`_last_actual_speed` calculé pour rien chaque
tick), `move_cost`, connectivité sparse. Seul code vraiment mort : `in_safe_zone()`
(tests only). Point faible réel = **perf** : raycast O(pop×rayons×pommes), ~15–25
ticks/s à capacité (15–30 min pour 15k–30k ticks).

### Fitness sharing NEAT câblé (2026-07-09)

Chantier n°1 de la feuille de route recherche (`speciation.py` calculait déjà
`compatibility_distance`/`count_species` mais uniquement pour le CSV + le choix
de partenaire crossover, jamais pour la sélection). Implémenté :
- `speciation.assign_species(genomes, config) -> list[int]` : même clustering
  glouton que `count_species`, mais renvoie l'id d'espèce par génome au lieu
  du seul décompte (`count_species` refactorée pour la réutiliser, zéro
  duplication de logique).
- `SpeciationConfig.fitness_sharing: bool = False` (rétro-compatible, comme
  `crossover_rate`/`initial_connectivity`) : off = comportement legacy
  identique bit à bit (aucun coût ajouté sur le chemin par défaut).
- `Simulation._priority_fn` : quand `fitness_sharing` est activé, divise la
  clé de tri de priorité de reproduction (énergie ou crédit forage cumulé)
  par la taille de l'espèce NEAT de l'agent (`f'_i = f_i / |espèce_i|`,
  formule canonique Stanley & Miikkulainen 2002) avant de trier les éligibles
  aux slots de repro rares — branché dans `_reproduce_by_energy` ET
  `_reproduce_by_foraging`. Le crédit/énergie réellement dépensé à la
  naissance n'est PAS modifié, seul l'ordre de priorité pour les slots change.
- 6 tests ajoutés (`test_speciation.py` : `assign_species` seul ;
  `test_simulation.py` : preuve d'intégration — une espèce isolée de taille 1
  bat une espèce dominante de taille 2 sur fitness partagée alors qu'elle
  perd sur fitness brute, ET preuve que `fitness_sharing: false` préserve
  l'ancien comportement dans le même scénario). 154 tests verts, pylint 10/10.
- Perf mesurée (`config/lever_fitness_sharing.yaml`, seed 42, pop pleine) :
  **18,02 ticks/s**, quasi identique aux 18,04 ticks/s sans (le calcul
  d'espèces ne tourne que dans la branche `slots > 0`, donc rarement à pleine
  capacité) — le recalcul périodique anticipé en amont n'a pas été
  nécessaire.

**Campagne de validation 3 seeds / 15k (2026-07-09) — FALSIFIÉ ❌**
(isolation à une variable, `config/lever_fitness_sharing.yaml` vs `default.yaml`,
% fourrageurs r>0,1) :

| Seed | Contrôle | Fitness Sharing | Δ | neurones cachés moy. (ctrl→FS) |
|------|:---:|:---:|:---:|:---:|
| 42   | **86 %** | 58 % | **−28** | 0,05 → **0,80** |
| 7    | 77 %     | 73 % | −4      | 0,13 → **0,97** |
| 123  | 42 %     | 46 % | +4      | 0,10 → **0,23** |
| **moyenne** | **68 %** | **59 %** | **−9** | |

**Même signature exacte que le crossover (volet 4) : un opérateur MOYENNANT.**
Aide marginalement le maillon faible (123 : +4) mais écrase le gagnant
historique (42 : −28), tirant tout le monde vers ~50-70 % ; la moyenne baisse
(68→59 %). Ne franchit PAS le 3/3 robuste de `apple_repro_bigpop`.

**Le détail mécanistique confirme que le fitness sharing marche exactement
comme prévu** — les neurones cachés moyens EXPLOSENT (42 : 0,05→0,80 ; 7 :
0,13→0,97) : il a bien **protégé l'innovation structurelle de l'écrasement**,
sa mission théorique. Mais cette structure protégée **n'améliore pas le
fourrage**, ce qui reconfirme le verdict du volet 3 (« les neurones cachés ne
discriminent PAS — le signal est le comportement, pas la structure »).
Protéger la structure protège quelque chose qui ne compte pas pour la tâche,
au prix de diluer le signal comportemental qui compte. **4e mécanisme
« réducteur » falsifié** (après crossover, capteur 67, sparse), tous du même
côté du pattern transverse : seul l'ADDITIF (population, sélection directe)
élève tous les seeds ensemble.

**Statut : câblé + testé + falsifié, non promu.** `default.yaml` garde
`fitness_sharing: false`. Mécanisme + `config/lever_fitness_sharing.yaml`
conservés comme référence d'expérience. Ne pas re-tenter comme levier de perf.

### poc2.4 — perf de simulation + nouveauté (2026-07-10)

**Perf** (`docs/DESIGN-poc2.4-perf.md`) : deux leviers composables pour accélérer
la boucle de recherche. (L1) `tools/campaign.py` lance les seeds en parallèle
(×2,64). (L2) `batch_sense` calcule la perception de toute la population en une
passe NumPy (tick « geler puis percevoir »), équivalence bit-à-bit, ×1,71
end-to-end ; combiné **×4,0**. Plafond restant = le forward pass NEAT hétérogène
(45 %), non batchable sans quitter NEAT.

**Nouveauté** (`docs/RESULTS-novelty.md`) : **1er levier positif du projet**, voir
§5. `src/novelty.py` + `NoveltyConfig` (section optionnelle), injection additive
dans `_priority_fn`. Promu en défaut (`weight 1.0`, `recompute_interval 10`).
168 tests verts, pylint 10/10.

**Archive de nouveauté — falsifiée** : suite tentée du levier précédent
(`novelty.archive_enabled`, pool persistant de comportements passés, injection
aléatoire p=0,01, Lehman & Stanley 2011). Campagne 6 seeds/15k, moy **62 %→55 %
(−7)**, régresse 4/6 seeds dont celui visé en priorité (99). Élargir le
voisinage avec du comportement obsolète dilue le signal de nouveauté vis-à-vis
de la sélection courante — **5ᵉ réducteur falsifié**, 1ᵉʳ déguisé en additif.
`archive_enabled` reste `false`. Voir `docs/RESULTS-novelty.md`.

**Nœud de biais NEAT — falsifiée, pire régression du projet** : point #5 de la
feuille de route, source constante 1.0 câblée à chaque sortie à la genèse
(`genome.bias_enabled`, `config/lever_bias.yaml`). Campagne 6 seeds/15k, moy
**62 %→28 % (−34)** : effondrement des seeds forts (42 : 86→13 ; 7 : 91→13 ;
5 : 87→30), léger mieux sur 2 seeds faibles (1, 99). Le biais injecte un
décalage constant et non situationnel dans les 2 sorties dès la naissance,
noyant le signal réactif piloté par les rayons — même famille que le volet 5/6
poc2.3 (ajouter une source au génome fondateur élargit la surface de mutation
initiale et casse la robustesse), en pire ici car permanent plutôt que
situationnel. `bias_enabled` reste `false`. 181 tests verts, pylint 10/10.

**Bug freeze ~100 ticks — corrigé** : signalé par Robin en jeu.
`mean_pairwise_distance` (diversité génétique, colonne CSV passive) tournait
en pur Python O(pop²), 318ms à pop≈400 — déclenché toutes les
`log_interval_ticks` (100), bien au-delà du budget d'une frame à 60 ticks/s.
Vectorisée en NumPy (`src/speciation.py`, même idée que
`batch_sense`/`population_novelty`) : **318→39ms (~8x)**. 182 tests verts.

**Densité agents/pommes — carte agrandie + vitesse ÷2, PROMU EN DÉFAUT** :
Robin a signalé un surpeuplement visible (pommes mangées par accident,
~0,2s de durée de vie). `tools/apple_capture_probe` confirme (54% de
captures non dirigées). Carte agrandie seule (×√2) améliore le symptôme
direct mais est mean-négative à l'évolution (62%→57%, 15k) — falsifiée.
Combinée à `agent.max_speed` divisé par 2 (moins de balayage/tick), la
campagne 15k reste sous le défaut (58%) mais **passe positive à 30k
(62%→66%, +4)**, avec un gain massif sur le seed historiquement le plus dur
(1 : 23%→58%). `default.yaml` promeut world 2263×1273→3200×1800 et
`max_speed` 4,243→2,122 ; population/pommes/capteurs inchangés —
`population.max_size` n'a volontairement pas été touché (poc2.2 ÉTAPES 7-10
ont déjà montré qu'une population plus petite rouvre la dérive fondatrice).
Voir `docs/RESULTS-density.md`.

**Critère minimal de reproduction — testé, falsifié** : Robin voulait une repro
non frénétique (réservée aux profils durablement compétents) et une pop qui
flotte dans une bande 400-500 au lieu d'être épinglée. Littérature de
neuroévolution non-épisodique (Soros & Stanley 2016 ; arXiv:2302.09334).
Nouveau `agent.reproduction_min_ticks` (0 = legacy) : un agent doit tenir un
crédit ≥ seuil N ticks consécutifs → **un** enfant → reset réfractaire.
`config/lever_min_criterion.yaml` (min_ticks 1000, max_size 500). **Campagne
30k/6 seeds (2026-07-15)** : forager% quasi neutre (62%→63%, +1, bruit),
**variance extrême** (seed 7 : 84→32, −52 ; seed 99 : 27→79, +52), et surtout
la population NE flotte PAS — tous les seeds terminent épinglés 488-500,
l'objectif principal n'est pas atteint. **6ᵉ réducteur falsifié**, profil
identique à fitness sharing/biais/archive. `default.yaml` garde le paramètre
absent (= 0). Voir `docs/FALSIFIED-min-criterion.md`.

**Troncature de sélection adoucie — testée, falsifiée, pas de bug (chantier
n°2)** : point #2 de la feuille de route, sauté par hypothèse en 2026-07-08,
repris et testé le 2026-07-15. `_reproduce_by_energy`/`_reproduce_by_foraging`
laissaient le meilleur agent drainer tous les slots d'un tick (boucle `while`)
avant même de regarder le 2ᵉ — littérature (Corus et al. 2021) : troncature
gloutonne = moteur mécanique d'effets fondateurs. Deux mécanismes câblés :
`agent.max_children_per_tick` (plafond plat, 0=legacy) et
`agent.reproduction_round_robin` (répartition breadth-first réelle via
`_round_robin_fill`, false=legacy — un agent seul sans concurrence reçoit
quand même tous les slots, contrairement au plafond plat). Sweep 1 seed/10k :
cap≥3 = no-op (jamais atteint), cap=1/2 sous la baseline ; round-robin
identique bit à bit à cap=1 (78% vs 82%). **Campagne 30k/6 seeds sur
round_robin** : mean **62%→65% (+3)** mais variance forte (seed 123 : 76→53,
−23 ; seed 1 : 23→56, +33) — **1er cas MIXTE du projet** (ni victoire nette
comme novelty, ni échec net comme les réducteurs). **Diagnostic CSV
tick-par-tick** (seed 123, demande explicite de Robin) : les deux trajectoires
sont identiques bit à bit jusqu'à ce que la population atteigne `max_size`
(~tick 3400), puis divergent car round-robin change l'ordre des naissances →
change l'ordre de consommation RNG (mutations) → cascade chaotique. **Pas de
bug** : même sensibilité aux effets fondateurs que crossover/fitness
sharing/biais/critère minimal. Décision Robin : **ne pas promouvoir**, même
profil de risque que les réducteurs à variance forte déjà écartés.
`default.yaml` garde les deux paramètres absents/legacy. Bonus livré :
`tools/campaign.py` affiche une progression périodique plain-text
(`--progress-interval`, `--quiet`). 202 tests verts, pylint 9.96/10. Voir
`docs/FALSIFIED-truncation.md`.

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
| `442256f` | poc2.3 : volet 6 — génome fondateur sparse, falsifié |
| `928ccb7` | audit : suppression code mort (clamp_velocity, Agent.update, Environment.respawn) |
| `9c56db2` | audit : retrait `population.min_size` (vestigial) |
| `702bc17` | poc2.4 perf L1 : runner de campagne parallèle (seeds en process, ×2,64) |
| `900bcb2` | poc2.4 perf L2 : perception batchée NumPy, tick « geler puis percevoir » (×1,71) |
| `6b18bc1` | poc2.4 : bonus de nouveauté additif — 1er levier NON falsifié (+10 sur 6 seeds) |
| `eaf6e72` | poc2.4 : nouveauté promue en défaut + recalcul périodique (sweep weight=1.0) |
| `282d3aa` | poc2.4 : archive de nouveauté câblée puis falsifiée (moy 62→55) |
| `6ef2938` | poc2.4 : nœud de biais NEAT câblé puis falsifiée (moy 62→28, pire régression) |
| `21c82a6` | poc2.4 : fix freeze ~100 ticks — mean_pairwise_distance vectorisée NumPy (318→39ms) |
| `b3b4afc` | poc2.4 : densité — carte agrandie + vitesse ÷2 promue en défaut (62%→66% @30k) |
| `0700645` | poc2.4 : critère minimal de reproduction câblé (non promu) |
| `70e7432` | poc2.4 : critère minimal falsifié — variance extrême, population épinglée |
| `fd5c116` | poc2.4 : troncature de sélection adoucie — testée, falsifiée, pas de bug |
