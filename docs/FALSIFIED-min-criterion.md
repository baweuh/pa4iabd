# Minimal-Criterion Reproduction — FALSIFIÉ (2026-07-15)

**Status** : ✅ COMPLET — falsification confirmée, non promu, `default.yaml` inchangé.

## Contexte & hypothèse

Demande de Robin (2026-07-10) : la reproduction est frénétique, la population épinglée à `max_size=400`. Souhait : limiter la repro aux profils « vraiment compétents » (crédit soutenu, pas juste du chance instantané), et laisser la population flotter dans une bande souple 400–500 sous le cap au lieu d'être exactement au plafond.

Littérature grounding : neuroévolution non-épisodique, critères minimaux de viabilité (Soros & Stanley 2016 « How the Strictness of the Minimal Criterion Impacts Open-Ended Evolution », arXiv:2302.09334 « Eco-evolutionary Dynamics of Non-episodic Neuroevolution »). Principes : (1) reproduction sur **crédit soutenu** pendant N ticks, pas instantané ; (2) population flotte sous un cap souple (naissances ≠ morts).

## Implémentation

**Commit** : `0700645` (feat(poc2.4): critère minimal de reproduction).

**Paramètre nouveau** : `agent.reproduction_min_ticks` (int, 0=legacy byte-identique).
- Valeur 0 : legacy (reproduction dès que crédit ≥ `apples_per_offspring`, pas de gate).
- Valeur N > 0 : agent reproduit ssi il a **tenu** crédit ≥ `apples_per_offspring` pour N ticks consécutifs. UN enfant produit, puis compteur `_credit_streak` reset (période réfractaire).

**Compteur `_credit_streak`** (`src/simulation.py`, ~ligne 320) : incrémenté chaque tick si crédit soutenu, reset si chute. Synchronisé avec `_repro_credit` (spawn → naissance → injection élite → mort).

**Config test** : `config/lever_min_criterion.yaml`
```yaml
agent.reproduction_min_ticks: 1000
population.max_size: 500  # raised from 400, target soft cap
```

**Tests** : 7 nouveaux (gate, un-enfant, reset, validation paramètre), 189 verts total, black + pylint clean.

## Résultats partiels (15k, 6 seeds)

| Metric | Default 15k | Min Criterion 15k |
|--------|-------------|------------------|
| Foragers% (mean) | 58% | 59% (300 ticks) / 58% (600 ticks) |
| Population end | 400 | 500 (épinglé) |

Observations : même à min_ticks=1000, la population restait épinglée (pop final ~485–495 vs cap 500), pas de bande flottante visible à 15k. Forager% neutre. Session coupée, campagne 30k décidée.

## Validation complète (30k, 6 seeds) — 2026-07-15

**Config** : `config/lever_min_criterion.yaml`, 30000 ticks, seeds 42/7/123/1/5/99.

> ⚠️ **BASELINE CORRIGÉE le 2026-07-22 (audit de traçabilité).** Ce document
> comparait à la ligne `62 %` (`82|84|76|23|81|27`), qui est le défaut
> **pré-densité**. Or `config/lever_min_criterion.yaml` porte `world 3200×1800`
> + `max_speed 2.122` (densité déjà promue) et `apples_per_offspring: 3.0` : la
> bonne référence est donc le défaut **post-densité, pré-K-sweep** = `66 %`
> (`85|77|61|58|85|32`), soit la ligne « carte+vitesse 30k » de
> `docs/RESULTS-density.md` et « défaut (K=3.0) 30k » de
> `docs/RESULTS-k-sweep.md` — le même run sous deux noms.
> **Le verdict (non promu) est inchangé, et même renforcé** : le levier passe de
> « +1 neutre » à **−3**.

**Baseline** : défaut post-densité K=3.0 30k (`docs/RESULTS-k-sweep.md`).

| Seed | Défaut K=3.0 30k | Min Criterion 30k | Δ | Verdict |
|------|-----------|------------------|---|---------|
| 42 | 85% | 90% | +5 | ✅ gain |
| 7 | 77% | 32% | **−45** | ❌ crash |
| 123 | 61% | 62% | +1 | ≈ stable |
| 1 | 58% | 37% | **−21** | ❌ perte |
| 5 | 85% | 79% | −6 | ❌ perte |
| 99 | 32% | 79% | **+47** | ✅ gain massif |
| **Mean** | **66%** | **63%** | **−3** | ❌ réducteur |

Population end : 488–500 (tous seeds épinglés au cap).

*(Pour mémoire, les Δ publiés jusqu'au 2026-07-22 contre la mauvaise baseline
étaient : +8 / −52 / −14 / +14 / −2 / +52, moyenne +1. La correction ne change
pas seulement la moyenne : le seed 1 passe de « +14 gain » à « −21 perte » et
le seed 123 de « −14 perte » à « +1 stable ».)*

## Analyse d'échec

**Signal 1 : Mean négative (−3 %)** — pas le gain espéré.
- Hypothèse falsifiée : « min_ticks≥1000 = sélection plus stricte = meilleur fourrage ».
- Explication : le gate retarde la repro d'agents qui ont du potentiel (long credit_streak requis) mais qui ne l'expriment pas tout de suite. D'autres agents compensent.

**Signal 2 : Variance extrême** (−45 / +47).
- Seed 7 : 77%→32%, dégradation massive. Compatible avec les autres leviers falsifiés :
  - `fitness_sharing` : moyenne −9 (68→59), seed 42 : 86→58
  - `bias_node` : pire régression jusqu'à HyperNEAT, moyenne −34 (62→28), seed 42 : 86→13
  - `archive_novelty` : variance modérée, moyenne −7 (62→55)
- Pattern : un levier qui « échange stabilité pour variance extrême » n'est jamais une victoire nette. Une seed gagne, une casse.

**Signal 3 : Population NOT flottante**.
- Objectif déclaré : « pop flotte en bande 400–500 ».
- Observé : pop épinglée à 488–500 (cap).
- Explanation : un gate de N=1000 ticks ralentit la repro suffisamment pour que les *morts* restent plus rapides que les *naissances*. Mais une fois qu'une pop stable de 400 ticks est atteinte, il n'y a plus de raison de flotter ; le gate maintient juste le plafond plus haut, la pop remonte au plafond. Le gate réfractaire crée une *stratégie de vie* (crédit soutenu → reproduction rare), pas une *dynamique de population* (naissances < morts).

## Classement en tant que réducteur

Ce levier rejoint la famille des **réducteurs**.

> ⚠️ **Liste entièrement réécrite le 2026-07-22 (audit de cohérence).** La
> version publiée jusque-là contenait **cinq chiffres faux**, dont un de signe
> inversé (le crossover y était donné à −15 % alors qu'il fait **+35**), et
> comparait des leviers de branches différentes à une baseline unique qui
> n'était valable pour aucun d'eux. Chaque ligne ci-dessous est désormais
> sourcée sur son document primaire, avec sa propre baseline et son protocole.

| # | Levier | Campagne | Baseline → résultat | Δ | Source |
|---|---|---|---|---|---|
| 1 | `crossover` (poc2.3) | 3 seeds / 15k | 30 % → 65 % | **+35** | `AUDIT-poc2.3.md` volet 3 |
| 2 | `crossover + bigpop` (poc2.3) | 3 seeds / 15k | 49 % (51/69/26) | — | `AUDIT-poc2.3.md` volet 4 |
| 3 | `sparse_init_genome` (poc2.3) | 3 seeds / 15k | 68 % → 24 % | **−44** | `AUDIT-poc2.3.md` volet 6 |
| 4 | `fitness_sharing` (2026-07-09) | 3 seeds / 15k | 68 % → 59 % | **−9** | `FALSIFIED-fitness-sharing.md` |
| 5 | `bias_node` (poc2.4) | 6 seeds / 15k | 62 % → 28 % | **−34** | `FALSIFIED-bias-node.md` |
| 6 | `archive_novelty` (poc2.4) | 6 seeds / 15k | 62 % → 55 % | **−7** | `RESULTS-novelty.md` |
| 7 | **`min_criterion`** (poc2.4) | 6 seeds / 30k | 66 % → 63 % | **−3** | ce document |

Deux précisions que l'ancienne liste écrasait :

- **Le crossover n'est PAS un réducteur en moyenne** — il monte de 30 à 65 %.
  Il a été écarté pour **non-robustesse** (le seed 123 régresse, 28 → 10 %),
  pas pour une moyenne négative. C'est un opérateur **moyennant** : il
  rapproche tous les seeds de ~50 % et réduit la variance inter-seeds.
- **`crossover + bigpop` n'a pas de Δ interprétable** contre un défaut : le
  point de la manip était de comparer la combinaison à **chaque levier seul**,
  et elle sous-performe les deux (crossover seul 65 %, bigpop seul 76 %,
  combinaison 49 %).

Le pattern reste : quand on essaie de « réduire » la population ou « écrêter » l'exploration, on échange la stabilité pour la variance. Les victoires du projet sont toutes des **ajouts** (`novelty` +10, densité +4, K-sweep +13 — aucun seed ne s'effondre).

## Leçon

Le pattern est clair :
- **Additifs** (plus d'information, plus de signaux) : marche (novelty +10 %).
- **Réducteurs** (gating, simplification, shrink) : échouent, ou n'améliorent
  la moyenne qu'en écrasant la variance (crossover), ce qui n'est pas la même
  chose qu'améliorer la compétence.
- Hypothèse : le système a atteint un minimum viable stable (population 400, capacité de charge, raycast efficace). Tout ce qui réduit *à l'intérieur* de ce régime déstabilise ; tout ce qui ajoute l'améliore.

## Artefact commit

```
docs(poc2.4): critère minimal falsifié — variance extrême, pop épinglée au cap
```

- PLAN.md : marquer ✅ falsifié
- `docs/FALSIFIED-min-criterion.md` : ce fichier
- `default.yaml` : `reproduction_min_ticks` reste absent (= 0, legacy)
- Memory update : `minimal-criterion-reproduction.md` → verdict
