# Modèle d'îles — FALSIFIÉ, réducteur net (poc2.4)

> Chantier B, piste notée dans `research-roadmap.md` comme alternative
> structurelle au crossover (falsifié). Implémenté, testé, câblé
> (`population.num_islands`, off par défaut = legacy), puis évalué par
> campagne — comme tous les leviers précédents du projet.

## Le mécanisme

`population.num_islands` (défaut 1) partitionne la population en N
sous-populations quasi-isolées, chacune avec son propre budget de slots de
reproduction (`max_size` divisé également), son propre classement de
priorité et son propre pool de partenaires (`_pick_mate`). Un petit nombre
d'agents (`migration_count`) migre vers l'île suivante sur un anneau fixe
tous les `migration_interval_ticks`. `num_islands=1` reproduit exactement le
comportement legacy (byte-à-byte, vérifié par les 216 tests existants
inchangés).

## Config testée

`config/lever_islands.yaml` = défaut courant (novelty + densité +
`apples_per_offspring=1.5`) + `num_islands=4` (100 agents/île),
`migration_interval_ticks=200`, `migration_count=2`.

## Campagne 6 seeds/30k

| seed | 42 | 7 | 123 | 1 | 5 | 99 | **moy** |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| défaut (K=1.5) 30k | 98 | 76 | 82 | 68 | 96 | 56 | **79** |
| îles (4×100) 30k | 93 | 48 | 74 | 57 | 90 | 48 | **68** |
| Δ | −5 | **−28** | −8 | −11 | −6 | −8 | **−11** |

**Les 6 seeds régressent, aucune exception.** Profil réducteur classique
(comme crossover, capteur 67, sparse init, fitness sharing, archive, biais,
critère minimal) — pas le profil additif (novelty, K-sweep) qui a
systématiquement marché dans ce projet.

## Diagnostic

Hypothèse mécanistique cohérente avec le reste du projet : découper 400
agents en 4 îles de 100 réintroduit la dérive fondatrice que poc2.2 ÉTAPES
7-10 avaient explicitement corrigée en passant de pop 200 à pop 400 (voir
`docs/Audits/AUDIT-poc2.2-v3.md`, ÉTAPE 8 : « une population plus PETITE
rouvre la dérive fondatrice »). Chaque île isolée est fonctionnellement une
population de 100 — plus petite que le seuil 200 déjà documenté comme
risqué, et bien en-deçà du régime robuste (400). La migration (2 agents/île
toutes les 200 ticks, débit total 8/200 ticks) est trop rare pour compenser :
elle mélange les lignées sans jamais élargir le pool de compétition effectif
au moment où la sélection agit.

## Décision

**Falsifié, non promu.** `default.yaml` garde `population.num_islands`
absent (=1, legacy). Le mécanisme reste câblé et testé (14 tests dédiés,
216 tests globaux verts, pylint 10/10) comme référence, au même titre que
crossover/fitness_sharing/bias/archive/min_criterion.

## Artefacts

- `src/config.py` : `PopulationConfig.num_islands/migration_interval_ticks/migration_count`
- `src/simulation.py` : `_island_capacities`, `_migrate`, boucle de
  reproduction par île, `_maybe_refresh_novelty` (refresh global unique par
  tick, indépendant du nombre d'îles)
- `tests/test_simulation.py`, `tests/test_config.py` : tests dédiés
- `config/lever_islands.yaml`
