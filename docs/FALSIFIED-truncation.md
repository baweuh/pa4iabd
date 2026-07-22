# Troncature de sélection adoucie — FALSIFIÉ (2026-07-15)

**Status** : ✅ COMPLET — pas de bug, sensibilité chaotique confirmée, non promu.

## Contexte & hypothèse

Chantier n°2 de la feuille de route recherche (mémoire `research-roadmap`, 2026-07-08) : les deux méthodes de reproduction (`_reproduce_by_energy`, `_reproduce_by_foraging`) trient les agents éligibles par priorité et laissent le TOP agent drainer tous les slots ouverts via une boucle `while`, avant même de considérer le suivant. La littérature (Corus et al. 2021) identifie précisément cette troncature gloutonne comme un moteur mécanique d'effets fondateurs / perte de diversité — cohérent avec le diagnostic du projet lui-même (poc2.2 ÉTAPES 7-10).

Chantier sauté le 2026-07-08 par hypothèse (« probable même échec réducteur »). Repris et testé empiriquement le 2026-07-15, à la suite de la clôture du chantier critère minimal.

## Implémentation — deux variantes

### (a) Plafond plat : `agent.max_children_per_tick`

`0` (défaut) = legacy illimité. `N > 0` : aucun agent ne peut produire plus de N enfants dans un même tick — force les slots qui seraient allés au top agent à se répartir vers le suivant.

Câblé dans `_reproduce_by_energy` et le chemin legacy (`min_ticks == 0`) de `_reproduce_by_foraging`, `src/simulation.py`.

### (b) Round-robin réel : `agent.reproduction_round_robin`

`false` (défaut) = legacy. `true` : répartition breadth-first via `_round_robin_fill` — les agents éligibles (ordre de priorité) reçoivent un enfant chacun par PASSE, avant qu'aucun n'en reçoive un 2ᵉ. Différence clé avec (a) : un agent SEUL (sans concurrence) reçoit quand même tous les slots disponibles, juste étalés sur plusieurs passes successives — pas de plafond artificiel quand il n'y a personne avec qui partager.

```python
def _round_robin_fill(self, eligible, slots, cap, step):
    children = []
    counts = {}
    remaining = list(eligible)
    while remaining and len(children) < slots:
        next_round = []
        for agent in remaining:
            if len(children) >= slots:
                break
            if cap and counts.get(agent, 0) >= cap:
                continue
            child = step(agent)
            if child is None:
                continue
            children.append(child)
            counts[agent] = counts.get(agent, 0) + 1
            next_round.append(agent)
        if not next_round:
            break
        remaining = next_round
    return children
```

Composable avec (a) : `cap` limite aussi le total par agent à travers les passes. Les deux sont no-op une fois `reproduction_min_ticks > 0` (le critère minimal limite déjà à 1 enfant/agent/tick).

**Tests** : 8 nouveaux (`test_simulation.py` : cap énergie/fourrage, spillover, round-robin split, no-ceiling sans compétition, legacy byte-identique ; `test_config.py` : validation/défauts), 202 verts, black clean, pylint 9.96/10 (3 warnings pré-existants dans `renderer.py`, non liés).

## Sweep 1 seed / 10k (seed 42) — signal précoce

| Config | Foragers% |
|--------|-----------|
| **Défaut (baseline)** | **82%** |
| cap=1 | 78% (−4) |
| cap=2 | 80% (−2) |
| cap=3 | 82% (=, no-op) |
| cap=5 | 82% (=, no-op) |
| cap=8 | 82% (=, no-op) |
| cap=10 | 82% (=, no-op) |
| round_robin=true | 78% (−4, **identique bit à bit à cap=1**) |

Cap≥3 ne s'active jamais sur ce seed (repro, record, steer score identiques au bit près à la baseline). Round-robin et cap=1 produisent des résultats identiques — signal que la divergence n'apparaît qu'en régime de compétition réelle, rare sur ce seed en 10k ticks.

## Campagne 30k (6 seeds) — round_robin (candidat le plus abouti)

> ⚠️ **BASELINE CORRIGÉE le 2026-07-22 (audit de traçabilité).** Ce document
> comparait à la ligne `62 %` (`82|84|76|23|81|27`), qui est le défaut
> **pré-densité**. Or `config/lever_round_robin.yaml` porte `world 3200×1800` +
> `max_speed 2.122` (densité déjà promue) et `apples_per_offspring: 3.0` : la
> bonne référence est le défaut **post-densité, pré-K-sweep** = `66 %`
> (`85|77|61|58|85|32`), soit « carte+vitesse 30k » dans
> `docs/RESULTS-density.md` = « défaut (K=3.0) 30k » dans
> `docs/RESULTS-k-sweep.md`. **Le verdict (non promu) est inchangé et
> renforcé** : le levier passe de « +3 » à **−1**, et n'est donc même plus un
> cas mixte à moyenne positive.

| Seed | Défaut K=3.0 30k | Round-robin 30k | Δ |
|------|-----------|-----------------|---|
| 42 | 85% | 80% | −5 |
| 7 | 77% | 70% | −7 |
| 123 | 61% | 53% | −8 |
| 1 | 58% | 56% | −2 |
| 5 | 85% | 92% | +7 |
| 99 | 32% | 38% | +6 |
| **Mean** | **66%** | **65%** | **−1** |

*(Δ publiés jusqu'au 2026-07-22 contre la mauvaise baseline : −2 / −14 / −23 /
+33 / +11 / +11, moyenne +3. La correction change la lecture du résultat :
ce n'était pas « moyenne positive mais variance forte » — c'est **4 seeds sur 6
qui régressent modérément**, pour une moyenne légèrement négative.)*

Population stable à 400 sur tous les seeds (pas de risque d'extinction). Contre la bonne baseline, le profil est celui d'un **réducteur modéré** : 4 seeds sur 6 régressent, aucun ne s'effondre, aucun ne gagne massivement — moyenne −1. (Contre la mauvaise baseline, ce résultat avait été lu comme le « premier cas mixte du projet », moyenne +3 avec un seed à −23 et un autre à +33. C'était un artefact de comparaison, pas une propriété du levier.)

## Diagnostic mécanique (seed 123, demande explicite de Robin)

Robin a demandé de comprendre MÉCANIQUEMENT pourquoi le seed 123 décroche (−8 contre la bonne baseline ; le chiffre de −23 qui a motivé la demande à l'époque venait de la mauvaise baseline). Deux runs headless complets (30k ticks, seed 123, config défaut vs `lever_round_robin.yaml`), CSV comparé tick par tick (`mean_forage_rate`, `species_count`, `max_generation`, population).

**Données brutes** (vérifiées le 2026-07-22, 301 lignes chacune) :
`logs/2026-07-15_134756/metrics.csv` (défaut) et
`logs/2026-07-15_135505/metrics.csv` (round-robin). `logs/` n'est pas versionné
— voir la note de traçabilité de `docs/SYNTHESE.md` §6.

**Constat** : les deux trajectoires CSV sont **identiques bit à bit jusqu'à tick ~3000-3400** — population, espèces, taux de fourrage, taille moyenne de réseau, tout correspond à 6 décimales près. C'est exactement le moment où la population atteint `max_size=400` pour la première fois.

**Explication** : pendant la phase de croissance (200→400 agents sur ~3400 ticks, ≈0,06 naissance/tick en moyenne), il y a quasiment toujours 0 ou 1 agent éligible par tick — round-robin et le greedy legacy sont alors mathématiquement identiques (rien à répartir s'il n'y a personne avec qui partager). Les deux mécanismes ne PEUVENT diverger qu'à partir du moment où une vraie compétition multi-agents apparaît, ce qui coïncide précisément avec le plafonnement de la population.

À partir de ce point, round-robin change l'**ordre** des naissances par rapport au greedy legacy → change l'ordre de consommation du générateur aléatoire (mutations à chaque naissance) → cascade en aval sur toutes les générations suivantes. C'est un phénomène de **sensibilité chaotique aux effets fondateurs**, pas un défaut structurel de round-robin : c'est le MÊME mécanisme qui explique la variance de tous les leviers précédents qui touchent à l'ordre ou aux poids de reproduction (crossover, fitness sharing, biais, critère minimal), documenté depuis les audits poc2.2. Round-robin ne fait que redistribuer différemment, par seed, la loterie de quelles mutations précoces gagnent la course à la domination — sans qu'aucun bug ne soit en cause.

## Décision

Robin, après diagnostic : **ne pas promouvoir**. La décision a été prise sur la lecture « gain moyen modeste (+3) ne compensant pas une régression de −23 sur un seed solide » ; contre la bonne baseline, elle est **encore mieux fondée** — il n'y a aucun gain moyen à mettre en balance (−1), et 4 seeds sur 6 régressent. Le seul critère qui a déjà fonctionné dans ce projet reste « aucun seed ne régresse » (novelty).

`default.yaml` garde `max_children_per_tick` (0) et `reproduction_round_robin` (false) absents/legacy.

## Classement

Ce chantier rejoint les réducteurs classiques (moyenne négative), avec un profil plus doux : pas d'effondrement, mais pas de gain non plus. Il confirme la même leçon structurelle : dans ce régime, tout ce qui touche à l'ORDRE ou au POIDS de la sélection expose le système à une sensibilité chaotique aux effets fondateurs, gagnante pour certains seeds, perdante pour d'autres, jamais un gain net et robuste. Seuls les leviers purement **additifs** (novelty) ont livré un gain sans contrepartie.

## Bonus livré au passage

`tools/campaign.py` affiche désormais une ligne de statut périodique (plain-text, pas de barre carriage-return) pendant l'exécution — `--progress-interval SECONDS` (défaut 10s), `--quiet` pour désactiver. Utile pour suivre une campagne longue en direct ou dans un log (`tee`), sans les artefacts d'une barre `\r`-based dans un fichier.

## Artefacts

- `src/config.py` : `AgentConfig.max_children_per_tick`, `AgentConfig.reproduction_round_robin`
- `src/simulation.py` : `_round_robin_fill`, intégration dans `_reproduce_by_energy` / `_reproduce_by_foraging`
- `tests/test_simulation.py`, `tests/test_config.py` : 8 nouveaux tests
- `tools/campaign.py` : progression périodique
- `config/lever_truncation_cap{1,2,3,5}.yaml`, `config/lever_round_robin.yaml`
  (les points `cap=8` et `cap=10` du sweep ont été testés par override, leurs
  configs n'ont pas été conservées — résultat identique à `cap≥3` : no-op pur)
- PLAN.md : entrée ✅ falsifiée
