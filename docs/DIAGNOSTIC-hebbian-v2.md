# Plasticité Hebbienne V2 (trace d'éligibilité + baseline) — FALSIFIÉE AU DIAGNOSTIC

**Statut : falsifiée, sans campagne 6 seeds. `hebbian.enabled` reste `false`.**
13ᵉ levier écarté, 2ᵉ sans brûler de campagne (après la mutation
auto-adaptative).

Date : 2026-07-20 (implémentation + diagnostic partiel) · **conclusion
2026-07-21** · branche `poc2.6` · suite de `docs/DIAGNOSTIC-hebbian-v1.md`

> ⚠️ **Ce document corrige une version antérieure de lui-même.** Le diagnostic
> partiel du 2026-07-20 (1 seed, 1 run, comparaison de moyennes de population)
> concluait « mode d'échec n°1 corrigé, mode n°2 non corrigé ». La matrice
> d'ablations complète ci-dessous montre que **les deux conclusions étaient
> fausses** — dans les deux sens. Ce qui a changé : une mesure **appariée par
> agent**, un **contrôle** qui n'existait pas, et un second seed.

## La règle

    e  <- eligibility_decay · e + x·y          (trace, par connexion)
    dw = learning_rate · (m − m̄) · e           (mise à jour contrastive)

Appliquée chaque tick, `m̄` = moyenne glissante de la récompense. Visait les deux
défauts diagnostiqués en V1 : la trace fait porter le crédit sur les ticks
d'**approche** plutôt que sur celui de la capture ; la baseline rend
l'apprentissage **contrastif**, donc une disette peut affaiblir une connexion.

`eligibility_decay = 0,99` (fenêtre ~100 ticks), calibré sur
`diagnostics.capture_lookback_ticks` = 134 (ticks pour traverser la portée
sensorielle à `max_speed`), et non le 0,9 habituel qui couvrirait moins d'un
dixième d'une approche.

## Ce qui manquait au diagnostic partiel, et qui change tout

### 1. Une mesure appariée — `tools/hebbian_probe.py`

La mesure inné-vs-appris n'existait dans **aucun outil versionné** : elle avait
été faite ad hoc, donc non reproductible. Elle est maintenant
`tools/hebbian_probe.py`, et elle est **appariée par agent** :

    APPRIS  steer_score(agent.network)                     — les poids plastiques
    INNÉ    steer_score(NeuralNetwork(agent.genome, ...))   — ce avec quoi il est né

L'apprentissage étant non-lamarckien, le génome porte toujours le câblage inné
et le réseau inné est reconstructible à tout instant.

Le diagnostic partiel comparait deux **moyennes de population** à des
checkpoints isolés. Sur une quantité aussi bruitée (le témoin lui-même va de
0,10 à 0,37 sur un même run), la différence de deux moyennes ne mesure rien. Le
delta par agent, lui, est un vrai appariement.

Second point de méthode : la règle étant `dw = lr·(m−m̄)·e`, un agent qui n'a
**jamais mangé** a `m = m̄ = 0` et ses poids ne bougent **pas du tout** — son
delta est exactement nul, pas petit. Avec ~3 pommes/vie médian, ces agents sont
majoritaires à tout instant : moyenner sur la population entière revient
surtout à moyenner des zéros. L'outil isole donc les agents dont les poids ont
réellement bougé (~80 % de la population à t=6000).

### 2. Un contrôle — et un bug qui le rendait inexprimable

`config/lever_hebbian_lr0.yaml` : plasticité **entièrement câblée**,
`learning_rate = 0`. Activer `hebbian` court-circuite les caches `steer_score`
et `behavior_descriptor` et fait scorer le réseau **vivant** par novelty (cf.
`Agent`) ; si ces effets de bord déplaçaient à eux seuls le score inné, tout le
« mode d'échec n°2 » serait un artefact du harnais et non un effet de
l'apprentissage. Ce contrôle n'avait jamais été fait.

Il ne pouvait d'ailleurs **pas** l'être : `HebbianConfig.__post_init__` exigeait
`learning_rate > 0`. Le doc précédent affirmait « chaque ingrédient est
ablatable en mettant son paramètre à 0 » — vrai pour `eligibility_decay` et
`baseline_rate`, **faux pour `learning_rate`**, et c'était précisément celui qui
manquait. Corrigé (`_require_non_negative`), avec un test qui verrouille les
trois ablations ensemble.

**Résultat du contrôle : `lr=0` est identique au témoin _ligne pour ligne_**,
sur les 6 checkpoints et les 2 seeds. Le harnais est sain, et tout écart observé
à `lr > 0` est bien causé par les poids qui bougent.

## Protocole

7 réglages × 2 seeds (42, 123) × 6000 ticks, checkpoints tous les 1000 ticks.
`python -m tools.hebbian_probe config/<cfg>.yaml 6000 <label> <seed> 1000`.

| config | rôle |
|---|---|
| `default.yaml` | témoin, pas de plasticité |
| `lever_hebbian_lr0.yaml` | contrôle du harnais (`lr = 0`) |
| `lever_hebbian_lr0.001.yaml` · `lr0.003.yaml` | sweep vers le bas |
| `lever_hebbian.yaml` | V2 de référence (`lr = 0,01`) |
| `lever_hebbian_trace_only.yaml` | ablation : `baseline_rate = 0` |
| `lever_hebbian_baseline_only.yaml` | ablation : `eligibility_decay = 0` |

## Résultat n°1 — l'apprentissage est un pile ou face

Taux de gagnants à t=6000, **parmi les agents dont les poids ont réellement
bougé** (~300-360 agents sur 400) :

| réglage | seed 42 | seed 123 |
|---|---|---|
| V2 lr=0,001 | 51 % | 55 % |
| V2 lr=0,003 | 43 % | 47 % |
| V2 lr=0,01 | 53 % | 41 % |
| ablation trace seule | 37 % | 53 % |
| ablation baseline seule | 67 % | 48 % |

**41–55 % à tous les réglages sur les deux seeds.** L'apprentissage n'a pas de
direction : autant d'agents s'améliorent que se dégradent. Le « mode n°1
corrigé » du diagnostic partiel n'était pas un effet, c'était le bruit de la
différence de deux moyennes.

Le delta moyen raconte la même chose autrement — positif tôt, nul ou négatif à
la fin :

| réglage | t=1000 | t=3000 | t=6000 |
|---|---|---|---|
| V2 lr=0,01 · seed 42 | +0,019 | +0,023 | **−0,002** |
| V2 lr=0,01 · seed 123 | +0,013 | +0,011 | **−0,001** |

Les gains précoces sont explicables sans invoquer d'apprentissage : à t=1000 le
score inné vaut ~0,08, et sur une population aussi mauvaise **n'importe quelle**
perturbation a une chance sur deux de ressembler à un progrès. Quand l'inné
devient bon (0,365 à t=6000), l'apprentissage n'apporte plus rien.

## Résultat n°2 — le dégât à l'évolution est dose-dépendant, pas structurel

`steer_inné` à t=6000, à comparer au témoin :

| réglage | seed 42 (témoin **0,365**) | seed 123 (témoin **0,057**) |
|---|---|---|
| contrôle lr=0 | 0,365 | 0,057 |
| V2 lr=0,001 | 0,333 | **0,063** |
| V2 lr=0,003 | 0,329 | 0,015 |
| V2 lr=0,01 | 0,268 | −0,021 |
| trace seule | 0,273 | −0,170 |
| baseline seule | 0,338 | 0,095 |

Le dégât décroît avec `lr` et **disparaît à `lr = 0,001`** (−0,032 sur seed 42,
+0,006 sur seed 123). L'hypothèse « hiding » du diagnostic partiel — le bruit
phénotypique masque les différences génétiques, donc *aucun réglage ne sauvera
le levier* — est donc **falsifiée elle aussi** : le réglage règle bien le
problème.

**Mais il le règle en éteignant l'apprentissage.** À `lr = 0,001` le delta moyen
vaut +0,005 pour 51 % de gagnants. Il n'existe aucune fenêtre où l'apprentissage
aide : soit il ne fait rien, soit il nuit.

Le fourrage de population confirme, monotone, aucun réglage ne battant le
témoin :

| réglage | foragers s42 | foragers s123 |
|---|---|---|
| témoin / contrôle lr=0 | 86 % | 48 % |
| lr=0,001 | 86 % | 45 % |
| lr=0,003 | 82 % | 41 % |
| lr=0,01 | 70 % | 36 % |
| trace seule | **50 %** | **16 %** |
| baseline seule | 76 % | 53 % |

## Résultat n°3 — les ablations : la trace fait l'amplitude, la baseline la borne

- **Trace seule** (pas de baseline) = renforcement positif pur avec crédit sur
  l'approche. **Diverge** : seed 42, delta −0,116 et fourrage 86 % → 50 %. C'est
  le mode d'emballement de V1, la trace ne faisant qu'accélérer sa course. La
  baseline est donc bien ce qui **borne** la dérive, exactement le rôle prévu.
- **Baseline seule** (pas de trace) = **inerte**. Delta +0,000 à +0,003 partout,
  inné le plus proche du témoin (0,338 / 0,095, au-dessus du témoin sur
  seed 123). Sans trace, il ne se passe rien : inoffensif et inutile.

V2 complète = borné (grâce à la baseline) mais sans direction (la trace apporte
de l'amplitude, pas du signal). D'où le pile ou face.

## Pourquoi — la vraie cause, et elle n'est pas dans la règle

Le crédit est attribué par une trace de ~100 ticks, dans une tâche qui délivre
**~3 récompenses par vie** (`docs/DIAGNOSTIC-hebbian-v1.md`) sur des vies de
plusieurs milliers de ticks. Quand une récompense arrive, la trace est dominée
par les ~100 derniers ticks de comportement, presque décorrélés de ce qui a
causé la capture. **L'attribution de crédit est du bruit.**

C'est une propriété de la **parcimonie de récompense de la tâche**, pas de la
forme de la règle. Aucune variante de règle Hebbienne (ABCD évolués, R-STDP
modulé, etc.) ne change le nombre d'événements informatifs par vie. Ce serait la
tâche qu'il faudrait changer — et Stanley, Bryant & Miikkulainen 2003 avaient
justement conçu leur domaine de foraging **pour exiger un changement de politique
en cours de vie**, ce que celui-ci ne fait pas : ici la bonne politique est la
même du premier au dernier tick, donc il n'y a rien à apprendre qui ne puisse
être inné.

## Pourquoi pas de campagne 6 seeds

Une campagne mesure le fourrage de population. Si le mécanisme individuel est un
pile ou face, il n'y a rien que la sélection puisse amplifier — et le fourrage
de population est déjà monotone décroissant avec `lr` sur les deux seeds. Brûler
6 seeds × 30k à **−37 % de perf** (47 → 30 ticks/s, mise à jour par tick et par
connexion) pour confirmer un pile ou face est exactement ce que la discipline du
projet évite.

## Rapport à la mutation auto-adaptative — le résultat transverse de poc2.6

Les deux leviers de la branche meurent du **même budget d'événements** :

| levier | événements informatifs disponibles | mécanisme tué |
|---|---|---|
| sigma auto-adaptatif | ~3 générations de profondeur de lignée / 6k ticks | sélection de **second ordre** |
| plasticité Hebbienne | ~3 pommes par vie | attribution de crédit **intra-vie** |

Même chiffre, même cause : **la tâche fournit de l'ordre de 3 événements
informatifs par agent**. Aucun mécanisme qui a besoin d'accumuler du signal —
que ce soit à travers ses enfants ou à travers sa propre vie — ne peut
fonctionner sur 3 événements. Le régime (`N_e` ≈ 82-90 sur pop 400, poc2.2) ne
laisse pas la marge.

Nuance importante par rapport à sigma : **c'est une falsification de la règle
ET du concept sur CETTE tâche**, pas seulement de la règle comme en V1. La V1
échouait par sa forme (crédit sur le tick de capture, pas de baseline) et sa
correction était identifiable ; V2 corrige bien la forme — les ablations le
prouvent, chaque ingrédient joue son rôle — et échoue quand même, faute de
signal à attribuer.

## Code

OFF par défaut, chemin legacy inchangé.

- `tools/hebbian_probe.py` — mesure inné/appris appariée (nouveau)
- `src/config.py` — `learning_rate = 0` accepté (`_require_non_negative`) : le
  contrôle du harnais était inexprimable
- `tests/test_config.py` — test verrouillant les 3 ablations à zéro
- `config/lever_hebbian_lr0.yaml`, `_lr0.001`, `_lr0.003`, `_trace_only`,
  `_baseline_only`

⚠️ Pièges consignés, valables pour toute reprise :
- Sous `hebbian.enabled`, les caches `steer_score` / `behavior_descriptor` sont
  contournés (`Agent`) — nécessaire, mais c'est exactement ce que le contrôle
  `lr=0` sert à disculper.
- `tools/hebbian_probe.py` flush explicitement : lancé en parallèle avec stdout
  redirigé, Python bufferise par blocs et aucun checkpoint n'est lisible avant
  la fin du process.
- Au passage V1→V2 les tests V1 passaient tous inchangés, V2 se réduisant à V1
  au premier appel (trace vide, baseline nulle). Corrigés + 7 tests V2.
