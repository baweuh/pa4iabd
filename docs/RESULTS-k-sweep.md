# K-sweep (apples_per_offspring) — meilleur résultat net du projet, promu en défaut (poc2.4)

> Point d'entrée poc2.2 ÉTAPE 10 (« valider N seeds + régler K ? »), resté ⬜
> dans `PLAN.md` depuis. Repris le 2026-07-15 après le constat que le défaut
> post-density+novelty n'est plus uniforme : seed 99 tombe à 32 % à 30k
> (`docs/RESULTS-density.md`) pendant que 42/5 tiennent 85-86 %.

## Le paramètre

`agent.apples_per_offspring` (K) — crédit de reproduction dépensé par enfant :
un agent banque +1 crédit par pomme mangée, dépense K crédit par naissance,
donc descendance lifetime ≈ pommes mangées / K, linéaire en compétence de
fourrage. Défaut historique K=3.0 (poc2.2 ÉTAPE 10 / poc2.3 volet 5).
Baisser K = naissances moins chères = turnover générationnel plus rapide par
pomme mangée = plus d'occasions pour la sélection d'agir par unité de
compétence.

## Sweep 15k (6 seeds, `tools/campaign.py`)

Base = `default.yaml` courant (novelty + densité inclus), seule
`apples_per_offspring` varie.

| K | 42 | 7 | 123 | 1 | 5 | 99 | **moy** |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| 1.5 | 95 | 54 | 60 | 56 | 82 | 55 | **67** |
| 2.0 | 92 | 59 | 65 | 46 | 81 | 56 | **66** |
| 2.5 | 90 | 52 | 47 | 44 | 85 | 55 | **62** |
| 3.0 (défaut) | 86 | 60 | 48 | 50 | 86 | 17 | **58** |
| 3.5 | 88 | 48 | 46 | 32 | 89 | 46 | **58** |
| 4.0 | 86 | 50 | 44 | 27 | 89 | 60 | **59** |
| 5.0 | 85 | 62 | 46 | 26 | 74 | 62 | **59** |

Tendance nette : plus K est bas, mieux c'est, jusqu'à un plateau sous 2.0.
K=1.5 gagne clairement, tiré surtout par le seed le plus faible du défaut
(99 : 17→55) sans casser les seeds forts.

## Confirmation 30k (décisif)

| seed | 42 | 7 | 123 | 1 | 5 | 99 | **moy** |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| défaut (K=3.0) 30k | 85 | 77 | 61 | 58 | 85 | 32 | **66** |
| K=1.5 30k | 98 | 76 | 82 | 68 | 96 | 56 | **79** |
| Δ | +13 | −1 | +21 | +10 | +11 | +24 | **+13** |

**5/6 seeds montent (jusqu'à +24 sur le pire du défaut), le 6e est quasi
stable (7 : 77→76, −1)** — même profil qualitatif que la novelty (aucun seed
ne s'effondre) mais un gain net supérieur à tous les leviers précédents
(novelty +10, densité +4). C'est le meilleur résultat net du projet à date.
L'effet ne s'érode PAS entre 15k et 30k, il s'amplifie (67→79) — signe d'un
effet structurel qui continue de composer avec le temps, pas d'un artefact
transitoire.

## Décision

**Promu.** `default.yaml` : `agent.apples_per_offspring` 3.0 → 1.5. Aucun
autre paramètre touché. 216 tests verts, black clean, pylint 10/10.

## Notes

- Le point bas de `PLAN.md` poc2.2 (« régler K pour remonter seed 123 ») est
  desormais obsolète dans son cadrage d'origine : à K=1.5, seed 123 n'est
  plus le plus faible (82 %) — c'est le sweep sur K, pas le ciblage d'un seed
  spécifique, qui a réglé le problème plus large.
- Hypothèse mécanistique non testée : K bas raccourcit le temps moyen entre
  deux naissances d'une même lignée compétente, donc plus de générations
  utiles dans une fenêtre de ticks donnée — cohérent avec le diagnostic
  poc2.2 (sélection ≪ mutation + dérive) : plus de générations = plus
  d'occasions pour la sélection de rattraper la dérive. À vérifier si besoin
  via le futur N_e (chantier D, instrumentation étendue).
