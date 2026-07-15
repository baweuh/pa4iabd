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
**Baseline comparaison** : `docs/RESULTS-density.md` (défaut 30k).

| Seed | Défaut 30k | Min Criterion 30k | Δ | Verdict |
|------|-----------|------------------|---|---------|
| 42 | 82% | 90% | +8 | ✅ gain |
| 7 | 84% | 32% | **−52** | ❌ crash |
| 123 | 76% | 62% | −14 | ❌ perte |
| 1 | 23% | 37% | +14 | ✅ gain |
| 5 | 81% | 79% | −2 | ❌ perte |
| 99 | 27% | 79% | **+52** | ✅ gain massif |
| **Mean** | **62%** | **63%** | **+1** | ⚠️ neutre/noise |

Population end : 488–500 (tous seeds épinglés au cap).

## Analyse d'échec

**Signal 1 : Mean neutre (+1 %)** — bruit de mesure.
- Hypothèse falsifiée : « min_ticks≥1000 = sélection stricte stricte = meilleur fourrage ».
- Explication : le gate retarde la repro d'agents qui ont du potentiel (long credit_streak requis) mais qui ne l'expriment pas tout de suite. D'autres agents compensent.

**Signal 2 : Variance extrême** (−52 / +52).
- Seed 7 : 84%→32%, dégradation massive. Compatible avec les autres leviers falsifiés :
  - `fitness_sharing` : variance −34 (bias_node pire), seed 42:86→58
  - `bias_node` : pire projet, seed 42:62→9 (÷7)
  - `archive_novelty` : variance modérée, moyenne−7
- Pattern : un levier qui « échange stabilité pour variance extrême » n'est jamais une victoire nette. Une seed gagne, une casse.

**Signal 3 : Population NOT flottante**.
- Objectif déclaré : « pop flotte en bande 400–500 ».
- Observé : pop épinglée à 488–500 (cap).
- Explanation : un gate de N=1000 ticks ralentit la repro suffisamment pour que les *morts* restent plus rapides que les *naissances*. Mais une fois qu'une pop stable de 400 ticks est atteinte, il n'y a plus de raison de flotter ; le gate maintient juste le plafond plus haut, la pop remonte au plafond. Le gate réfractaire crée une *stratégie de vie* (crédit soutenu → reproduction rare), pas une *dynamique de population* (naissances < morts).

## Classement en tant que réducteur

Ce levier est le **6e mécanisme falsifié** du projet, et rejoint la famille des **réducteurs** :

1. `crossover` (poc2.3) : moyenne −15 % (62%→47%)
2. `crossover + bigpop` (poc2.3) : moyenne −18 % (62%→44%)
3. `sparse_init_genome` (poc2.3) : moyenne −34 % (seule tentative génome)
4. `fitness_sharing` (poc2.4) : moyenne −9 % (62%→53%), seed 42 −28
5. `bias_node` (poc2.4) : moyenne −34 % (62%→28%), **pire du projet**
6. `archive_novelty` (poc2.4) : moyenne −7 % (62%→55%)
7. **`min_criterion`** (poc2.4) : moyenne +1 % (62%→63%), **mais variance extrême** (−52/+52)

Le pattern est uniforme : quand on essaie de « réduire » la population ou « écrêter » l'exploration, on échange la stabilité pour la variance. La seule victoire du projet est l'**ajout** (`novelty` : +10 %, tous seeds up ou stable).

## Leçon

Après 6 falsifications, le pattern est clair :
- **Additifs** (plus d'information, plus de signaux) : marche (novelty +10 %).
- **Réducteurs** (gating, simplification, crossover, shrink) : échouent toujours.
- Hypothèse : le système a atteint un minimum viable stable (population 400, capacité de charge, raycast efficace). Tout ce qui réduit *à l'intérieur* de ce régime déstabilise ; tout ce qui ajoute l'améliore.

## Artefact commit

```
docs(poc2.4): critère minimal falsifié — variance extrême, pop épinglée au cap
```

- PLAN.md : marquer ✅ falsifié
- `docs/FALSIFIED-min-criterion.md` : ce fichier
- `default.yaml` : `reproduction_min_ticks` reste absent (= 0, legacy)
- Memory update : `minimal-criterion-reproduction.md` → verdict
