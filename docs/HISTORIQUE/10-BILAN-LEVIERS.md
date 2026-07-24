# 10 — Bilan complet : les 17 leviers + les limites assumées

> Le tableau maître, dense, réutilisable tel quel en annexe de mémoire.
> **13 leviers écartés, 4 promus.** Chaque ligne renvoie au chapitre de branche
> pour le détail. Source : `SYNTHESE.md §6bis`, `PLAN.md`.

---

## Convention de comptage

Sans elle, le total « 13 / 4 » est ambigu. Trois règles :
1. les **versions successives d'un même mécanisme** comptent pour **un** levier
   (HyperNEAT V1→V4 = 1 ; Hebbien V1→V2 = 1 ; plafond plat + round-robin = 1) ;
2. les **réglages purement paramétriques** de poc2.2 (mutation, drain,
   `max_energy`, densité de nourriture, `move_cost`) **ne comptent pas** — ils
   relèvent de la calibration, pas d'un levier de mécanisme (les compter ajouterait
   ~8 falsifications) ;
3. « **carte agrandie seule** » n'est pas un levier écarté : c'est la première
   moitié du levier densité, finalement promu sous la forme « carte + vitesse ÷2 ».

---

## Les 4 leviers PROMUS

Tous **additifs**, tous liés à l'**échelle ou à l'écologie**. Aucun n'agit sur le
mécanisme de sélection.

| # | Levier | Branche | Gain | Catégorie | Chap. | Document primaire |
|---|---|---|---|---|---|---|
| 1 | Repro ∝ pommes cumulées **+** population 200→400 | poc2.2 | percée fondatrice — 1ʳᵉ émergence robuste ET stable | écologie + sélection directe | `04` | `Audits/AUDIT-poc2.2-v3.md` |
| 2 | Novelty search (bonus additif) | poc2.4 | 52 → 62 % (**+10**), aucun seed ne régresse | additif / exploration | `06` | `RESULTS-novelty.md` |
| 3 | Densité — carte ×√2 + `max_speed` ÷2 | poc2.4 | 62 → 66 % (**+4** @30k) | écologie | `06` | `RESULTS-density.md` |
| 4 | K-sweep — `apples_per_offspring` 3.0 → 1.5 | poc2.4 | 66 → 79 % (**+13**), 5/6 seeds montent | sélection directe / écologie | `06` | `RESULTS-k-sweep.md` |

**Bilan bout-en-bout : 52 % → 79 % de fourrageurs** (6 seeds) entre le défaut
poc2.3 et le défaut de clôture.
⚠️ **Attention en le citant** : les gains intermédiaires sont mesurés à des
horizons différents (novelty à 15k ; densité et K-sweep à 30k) et chacun sur la
baseline qui le précède — **ils ne s'additionnent pas arithmétiquement** (10+4+13
≠ 27).

---

## Les 13 leviers ÉCARTÉS

| # | Levier | Branche | Campagne | Résultat | Catégorie | Chap. | Document |
|---|---|---|---|---|---|---|---|
| 1 | Crossover NEAT intra-espèce | poc2.3 | 3 seeds / 15k | 30 → 65 % (**+35**) mais **non robuste** (123 : 28→10) | sélection/repro | `05` | `AUDIT-poc2.3.md` v3 |
| 2 | Crossover + bigpop | poc2.3 | 3 seeds / 15k | **49 %** — sous chaque levier seul (65 / 76) | sélection/repro | `05` | `AUDIT-poc2.3.md` v4 |
| 3 | Capteur 67 entrées | poc2.3 | 3 seeds / 15k | casse la robustesse (123 : 43→1) | génome/encodage | `05` | `AUDIT-poc2.3.md` v5 |
| 4 | Génome fondateur sparse | poc2.3 | 3 seeds / 15k | 68 → 24 % (**−44**) | génome/encodage | `05` | `AUDIT-poc2.3.md` v6 |
| 5 | Fitness sharing NEAT | poc2.3 (2026-07-09) | 3 seeds / 15k | 68 → 59 % (−9) | sélection/repro | `05` | `FALSIFIED-fitness-sharing.md` |
| 6 | Archive de nouveauté | poc2.4 | 6 seeds / 15k | 62 → 55 % (−7) | sélection/repro | `06` | `RESULTS-novelty.md` |
| 7 | Nœud de biais NEAT | poc2.4 | 6 seeds / 15k | 62 → 28 % (**−34**) | génome/encodage | `06` | `FALSIFIED-bias-node.md` |
| 8 | Critère minimal de repro | poc2.4 | 6 seeds / 30k | 66 → 63 % (−3) | sélection/repro | `06` | `FALSIFIED-min-criterion.md` |
| 9 | Troncature adoucie | poc2.4 | 6 seeds / 30k | 66 → 65 % (−1), **mixte** | sélection/repro | `06` | `FALSIFIED-truncation.md` |
| 10 | Modèle d'îles | poc2.4 | 6 seeds / 30k | 79 → 68 % (−11), **les 6 seeds régressent** | sélection/repro | `06` | `FALSIFIED-islands.md` |
| 11 | HyperNEAT (V1→V4) | poc2.5 | 4 × 6 seeds | meilleur = V3 : 79 → 68 % ; V1 −52 ; V4 non monotone | génome/encodage | `07` | `FALSIFIED-hyperneat.md` |
| 12 | Mutation auto-adaptative (sigma ES) | poc2.6 | **diagnostic, sans campagne** | sigma dérive sans s'auto-régler | régime de variation | `09` | `DIAGNOSTIC-self-adaptive-mutation.md` |
| 13 | Plasticité Hebbienne (V1+V2) | poc2.6 | **diagnostic, sans campagne** | 41-55 % de gagnants = pile ou face | intra-vie | `09` | `DIAGNOSTIC-hebbian-v1/v2.md` |

---

## Ce que le tableau montre d'un coup d'œil

1. **Aucun levier agissant sur le mécanisme de sélection n'a jamais été promu,
   sur 13 tentatives.** Crossover, fitness sharing, archive, critère minimal,
   troncature, îles — tous du même côté du fil rouge.
2. **Les 4 promus sont tous additifs et tiennent tous à l'échelle/l'écologie.**
   Population, novelty (additif), densité (écologie), K (renouvellement
   générationnel).
3. **Les réducteurs ont une signature commune** : ils **moyennent** (rapprochent
   les seeds de ~50 %) au lieu d'amplifier — parfois en aidant marginalement le
   maillon faible, toujours en écrasant les gagnants.
4. **Les 2 derniers (poc2.6) échappent au clivage sélection/écologie** : ils
   échouent pour une raison encore plus profonde — la tâche ne fournit que ~3
   événements informatifs par agent (`09`).

---

## Répartition par catégorie (pour la soutenance)

| Catégorie | Écartés | Promus |
|---|---|---|
| Sélection / reproduction | 1,2,5,6,8,9,10 (7) | (partie de #1, #4) |
| Génome / encodage fondateur | 3,4,7,11 (4) | — |
| Régime de variation | 12 (1) | — |
| Apprentissage intra-vie | 13 (1) | — |
| Écologie / échelle | — | #1 (pop), #3 (densité), #4 (K) |
| Exploration additive | — | #2 (novelty) |

---

## Les 3 limites assumées (pistes non explorées, avec la raison)

Ce ne sont **pas un backlog** — ce sont des pistes délibérément non engagées,
chacune avec sa raison. Elles définissent le périmètre honnête du travail.

1. **HyperNEAT V5 — régime de mutation CPPN dédié.** Diagnostic établi
   (V2/V3) : le CPPN progresse à peine structurellement avec le régime de mutation
   hérité de l'encodage direct, jamais ajusté pour un génome à 6-14 poids fortement
   couplés. **Bien scopée, coût connu.** Non explorée car le chantier HyperNEAT a
   été clos sur la non-monotonie V3→V4 qui rend le levier imprévisible avant
   affinage. → `07`.
2. **Repro non canonique.** Deux écarts à la littérature repérés en audit, jamais
   testés : `Genome.crossover` traite toujours `self` comme parent « fitter » sans
   comparer les fitness ; la reproduction ne comble que les slots vidés par la mort
   (pas de turnover forcé façon rtNEAT). Non explorée : **catégorie repro, dont
   tous les représentants ont échoué** (troncature, critère minimal, îles,
   crossover), et aucun diagnostic ne motive spécifiquement l'un ou l'autre.
3. **Quality-Diversity — MAP-Elites / NSLC** (Lehman & Stanley 2011 ;
   Mouret & Clune 2015) **et ALPS** (Hornby 2006). NSLC combine novelty (déjà
   promu) avec une compétition **locale** ; ALPS protège les jeunes génotypes par
   couches d'âge. Non explorées : toutes deux **restructurent la sélection pour
   préserver la diversité** — l'objectif exact des îles, falsifiées parce que 4
   îles de 100 rouvrent la dérive fondatrice. Elles n'auraient de sens qu'à une
   population assez grande pour que subdiviser ne coûte pas la dérive → **elles
   dépendent de l'hypothèse d'échelle, la limite non testée du travail** (`08`).

**Sur les leviers « ML »** : la contrainte « aucun framework ML » est levée depuis
le 2026-07-20 (`neat-python`/`gym` restant interdits). Les 2 leviers de poc2.6
étaient de toute façon du NumPy à la main. Un RL classique reste hors cadre (boucle
d'entraînement séparée, tension avec « feedforward + évolution seule ») — et le
résultat de poc2.6 suggère qu'il buterait sur le même mur (~3 récompenses/vie).
