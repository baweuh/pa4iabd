# Novelty search — 1er levier positif du projet, promu en défaut (poc2.4)

> Chantier n°3 de la feuille de route recherche. Après **4 mécanismes réducteurs
> tous falsifiés** (crossover, capteur 67, génome sparse, fitness sharing — tous
> « moyennent / diluent la variance »), le bonus de nouveauté **additif** est le
> premier levier qui améliore vraiment le fourrage. Promu en `default.yaml`.

## Le mécanisme

Novelty search (Lehman & Stanley 2011), câblé comme **bonus ADDITIF** sur la
priorité de reproduction — jamais en remplacement de la fitness.

- **Descripteur comportemental** (`src/novelty.py::behavior_descriptor`) : le
  profil de réponse en virage du réseau, `tanh(sortie_virage)` à une pomme placée
  sur chaque rayon. Déterministe du réseau (poids figés) → **caché une fois par
  agent** (`Agent.behavior_descriptor`, comme le tri topologique).
- **Nouveauté** (`population_novelty`) : distance moyenne aux `k` plus proches
  comportements de la population (NumPy, pairwise).
- **Injection** (`Simulation._priority_fn`) : `priorité += weight × moy(fitness) ×
  nouveauté_normalisée[0,1]`. Bornée, **non négative** (ne pénalise jamais).
  Compose avec le fitness sharing ; off = retourne la fitness brute (coût nul).

Pourquoi additif : c'est le **seul pattern qui a tenu** sur ce projet. Tout
mécanisme réducteur écrasait un seed. Un bonus (jamais une pénalité) respecte ça.

## Le verdict — campagne 6 seeds / 15k (`tools/campaign.py`)

% d'agents fourrageurs (steer r>0,1), novelty w=1.0 vs `default` d'avant :

| seed | 42 | 7 | 123 | 1 | 5 | 99 | **moy** |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| avant | 88 | 74 | 56 | 9 | 81 | 6 | **52** |
| novelty | 88 | 88 | 61 | 20 | 89 | 29 | **62** |
| Δ | 0 | +14 | +5 | +11 | +8 | +23 | **+10** |

**Chaque seed monte ou tient, aucun ne régresse.** Les seeds durs que le défaut
rate presque (1, 99) sont les plus aidés. 6 seeds cohérents ≠ bruit. La structure
n'explose pas (cachées ~0,1) → il diversifie le **comportement**, pas la topologie.

## Le sweep de `weight` — optimum franc à 1.0

| weight | 0 (déf) | 0.3 | 0.5 | **1.0** | 2.0 |
|---|:--:|:--:|:--:|:--:|:--:|
| moy 6 seeds | 52 | 59 | 61 | **62** | 54 |

Courbe en cloche : à 2.0 la nouveauté **dilue** la sélection sur le forage (seed 42 :
88→78, steer_med +0,54→+0,29). Plateau robuste 0.5–1.0, pic à **1.0**.

## L'optimisation perf — recalcul périodique

La nouveauté est en O(pop²)/tick de repro → ~−34 % de débit en solo (104→71 ticks/s).
`recompute_interval` amortit le scoring O(pop²) sur N ticks (le comportement dérive
lentement : quelques naissances/morts par tick sur 400) ; l'application du bonus
reste par tick. Balayage de l'intervalle (6 seeds) :

| intervalle | 1 (exact) | 10 | 25 |
|---|:--:|:--:|:--:|
| moy 6 seeds | 62 | **62** | 60 |
| débit solo (ticks/s) | 71 | **113** | 122 |

**`recompute_interval: 10`** = plein gain (+10) **au débit de base**. Retenu pour le défaut.

## Promotion

`config/default.yaml` active désormais :
```yaml
novelty:
  enabled: true
  weight: 1.0
  neighbors: 15
  recompute_interval: 10
```
Section YAML **optionnelle** (absente → off) → toutes les configs antérieures
chargent inchangées. Verdict et mécanisme préservés comme référence dans
`config/lever_novelty.yaml`. Tests : `tests/test_novelty.py` (équivalence,
additivité, optionnalité, gate du recalcul).

## Suites possibles

- Les seeds durs (1, 99) restent bas en absolu (20–27 %) : aidés, pas « résolus ».

## Piste testée — archive de nouveauté : FALSIFIÉE

Le novelty search canonique (Lehman & Stanley 2011) garde une archive des
comportements passés, pas seulement la population courante. Hypothèse : sur les
seeds durs (1, 99), une fois la population vivante convergée il n'y a plus rien
de novateur pour s'en écarter — une archive persistante élargirait le
voisinage. Câblé dans `novelty.archive_enabled` (`src/novelty.py::
population_novelty`, injection aléatoire p=0,01 par agent scoré, FIFO cap 500,
`config/lever_novelty_archive.yaml`), isolé à **une seule** différence vs
`default.yaml`.

Campagne 6 seeds/15k, archive vs défaut (novelty sans archive) :

| seed | 42 | 7 | 123 | 1 | 5 | 99 | **moy** |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| défaut | 86 | 91 | 55 | 27 | 87 | 25 | **62** |
| archive | 75 | 73 | 42 | 32 | 89 | 18 | **55** |
| Δ | −11 | −18 | −13 | +5 | +2 | −7 | **−7** |

**Régresse 4/6 seeds**, et surtout régresse le seed qu'elle visait le plus
(99, le pire en absolu : 25→18). Les deux légers gains (1, 5) ne compensent
pas. Diagnostic : élargir le voisinage avec des comportements obsolètes dilue
le signal de nouveauté vis-à-vis de la pression de sélection **courante** —
même symptôme « moyennant » que les 4 mécanismes réducteurs déjà falsifiés
(crossover, capteur 67, génome sparse, fitness sharing), malgré une
construction additive en apparence (la bonus reste ≥ 0 par construction, mais
le signal qu'il ajoute est bruité par du passé non pertinent). 5ᵉ mécanisme
réducteur falsifié sur ce projet — le 1ᵉʳ à se déguiser en levier additif.

`novelty.archive_enabled` reste `false` par défaut ; mécanisme gardé câblé et
testé (`tests/test_novelty.py`) comme référence, non promu.
