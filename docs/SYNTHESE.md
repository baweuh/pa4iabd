# Synthèse du projet — ALife Neuroevolution

> Vue d'ensemble transverse : de la fondation technique (Phases 1-8) à la branche
> `poc2.3`. Pour le détail, voir `docs/Phase/*` (implémentation) et
> `docs/Audits/AUDIT-poc2.2-v3.md` + `AUDIT-poc2.3.md` (investigations).
> Rédigé le 2026-07-08.

---

## 1. La trajectoire en un coup d'œil

```
Juin 10-12   Phases 1-8      Le simulateur (génome NEAT, réseau, agent, sim, rendu, CLI)
   ↓         poc2.1          Équilibrage énergie, calibration zone pénalité, logging/run
   ↓
Juil 6-7     poc2.2          INVESTIGATION : « pourquoi ça n'évolue pas ? » (ÉTAPES 0-10)
   ↓                         → Diagnostic + 1ère émergence robuste (apple_repro + bigpop)
   ↓
Juil 7-8     poc2.3          Capteurs 67 + viz réseau, puis 3 relances structurelles :
                             volet 1 (perception) ✅ · volet 2 (mutation) ❌ · volet 3 (crossover) 🟢
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

## 4. poc2.3 — capteurs, visualisation, trois relances

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

**Expérience — 3 runs, seed 42, 30k, isolation à une variable :**

| | Contrôle | **Lever C (crossover)** | Lever B (bigpop) |
|---|---|---|---|
| Diffère du contrôle par | — | `crossover_rate` seul | population seule |
| Fourrageurs (r>0.1) | **9/200 (4 %)** | **177/200 (88 %)** | 302/400 (76 %) |
| Steer moyen | −0,284 | +0,366 | +0,232 |
| Cachés (moy. **population**) | 0,83 | 0,76 | 0,52 |

**Deux résultats :**
1. **À population identique, le crossover fait 4 % → 88 % (22×)** — effet propre,
   isolé du levier population.
2. **Les neurones cachés ne discriminent PAS** : le contrôle en porte autant tout
   en étant anti-fourrageur. La population *porte* des cachés qui ne deviennent
   jamais champions (Cause 3 de poc2.2) → aucun avantage de fitness. **Le signal
   est le comportement, pas la structure.**

Sorties brutes : `logs/2026-07-08_crossover/` (seed 42).

---

## 5. Où on en est / décisions ouvertes

- 🟢 **Crossover = résultat le plus fort du projet** pour débloquer le fourrage à
  petite population — mais **single-seed (42)**. La leçon de poc2.2 étant que les
  régimes rebrassent les seeds, **la robustesse 3 seeds reste à confirmer**.
- ⬜ **Robustesse** : relancer `{lever_crossover, default}` sur seeds 123 et 7.
- ⬜ **Promotion défaut** : `default.yaml` reste `crossover_rate 0.0`. Décision
  ouverte (crossover en défaut ? campagne 3 seeds complète avec Lever B ?).

---

## 6. État du code & qualité

- **148 tests verts**, `pylint 10/10`, `black` clean.
- Invariants respectés : 67 inputs (code = CLAUDE.md), feedforward garanti dans
  crossover, spéciation câblée dans le choix du partenaire.
- Isolation expérimentale **rigoureuse** : chaque levier = une seule variable
  modifiée depuis le contrôle.

## 7. Historique des commits clés

| Commit | Objet |
|--------|-------|
| `009f2dc` | poc2.2 ÉTAPE 10 : repro ∝ pommes cumulées (1ère émergence robuste+stable) |
| `fa2656e` | poc2.3 : capteurs 67, proprioception, viz réseau (+ défaut apple_repro 5.0) |
| `804d3c5` | poc2.3 : audit clôture — relance par mutation falsifiée |
| `68305c2` | poc2.3 : crossover NEAT intra-espèce (Lever C) |
| `0b12070` | poc2.3 : audit volet 3 — le crossover débloque le fourrage (seed 42) |
