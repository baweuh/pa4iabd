# 08 — poc3 : l'hypothèse d'échelle — architecture livrée, hypothèse jamais tranchée

> Branche latérale, 2026-07-16 → 2026-07-20, **abandonnée définitivement le
> 2026-07-22.** C'est le **seul grand axe du projet sans verdict** — la *limite
> assumée* du travail. Sources : `PLAN.md §poc3`, `SYNTHESE.md §6`. ⚠️ Les
> invariants n°3/n°4 diffèrent sur poc3 (topologie FIXE) ; **seule
> l'architecture poc2.x fait foi**, poc3 étant abandonnée.

---

## Intention

Un constat net motive la branche : **les 4 seuls leviers positifs du projet**
(population 200→400, K-sweep, densité, novelty) tiennent **tous** à
l'**échelle / l'écologie**, jamais au mécanisme de sélection. Et la littérature du
même paradigme (Hamon et al. 2023 ; Bejjani et al. 2025, **60 000+ agents**)
rapporte des comportements qui **n'émergent qu'au-delà d'un seuil de taille de
population**.

**Hypothèse** : et si le fourrage vraiment robuste demandait simplement **beaucoup
plus d'agents** ?

**Verrou technique identifié** : le forward pass NEAT hétérogène, non batchable,
consomme 45 % du tick — payé pour une topologie qui **n'évolue quasiment jamais**
(<0,5 nœud caché en moyenne après 30k ticks). On paie cher une flexibilité
structurelle qu'on n'utilise pas.

---

## Ce qui a été fait — l'architecture (livrée et mesurée ✅)

Décision radicale : **abandonner le NEAT structurel** pour débloquer l'échelle.
- **Topologie FIXE** (`network.hidden_size`, plus aucune mutation structurelle,
  seuls les poids évoluent) → le réseau devient une pile de couches en série, donc
  **batchable**.
- **`batch_activate`** : forward pass de toute la population en une passe → le
  verrou passe de **45 % à 2,8 %** du tick.
- **`batch_eat`** + **`novelty.max_pool_size`** : débloquent l'échelle réelle
  (le scoring de novelty O(pop²) devient le nouveau goulot à grande pop).

**Débit obtenu** : 400 agents → 106 ticks/s ; 4000 → 19,3 ; **16 000 → 6,7** —
l'échelle devient **jouable** jusqu'à ~16k agents.

> ⚠️ Conséquence architecturale : `src/hyperneat.py` et son outillage ont été
> **supprimés** sur poc3 (incompatibles avec la topologie fixe). C'est pourquoi
> les invariants n°3/n°4 diffèrent entre poc2.x et poc3.

---

## Ce qui n'a PAS été fait — l'hypothèse d'échelle elle-même (⛔ sans verdict)

**L'architecture est livrée. L'hypothèse qui a motivé la branche n'a jamais été
tranchée.**

- **Round 1** (pop 400 → 4000, 6 seeds/30k) : régresse à **38 %** de fourrageurs
  (54/31/49/27/38/30), mais le résultat est **confondu et donc inexploitable** —
  4000 agents pour **160 pommes inchangées** (compétition ~5× plus dense), et la
  population **n'a jamais dépassé `initial_size`** (1943-2010 sur un cap de 4000).
  **Le régime visé n'a pas été atteint.**
- **Round 2** (pommes ×10, conçu *précisément* pour lever ce confound) :
  **interrompu à 4 %.**
- S'ajoute que **`novelty.max_pool_size`**, l'approximation qui rend l'échelle
  jouable, **dégradait −12 pp à pop 400 et n'a jamais été validée** — donc même
  les runs à grande échelle utilisent une approximation non contrôlée.

**Ces deux mesures manquantes ne seront pas produites.** C'est exactement pourquoi
**aucun verdict d'échelle n'est revendiqué**.

---

## Diagnostic / pourquoi c'est notable

Ce n'est pas un échec technique — l'archi marche. C'est une **question restée
ouverte** :

1. **C'est le seul axe du projet sans conclusion.** Tous les autres (sélection,
   encodage, écologie) ont un verdict. L'échelle, non.
2. **C'est aussi la direction qui a le mieux marché.** 4 des 5 leviers promus
   tiennent à l'échelle ou à l'écologie — donc « pousser l'échelle » était
   *l'extrapolation la plus naturelle* du succès du projet. Ne pas l'avoir
   tranchée, c'est ignorer jusqu'où porte la direction la plus prometteuse.
3. **Le projet sait ce qu'il n'a pas démontré.** C'est une honnêteté assumée, pas
   un oubli caché — d'où la formulation « **limite assumée** ».

---

## Données brutes (les deux seules campagnes poc3 sont traçables)

- Round 1 : `logs/campaign_runs/scale4000_20260716_200310.log` +
  `logs/seed*/2026-07-16_200310/` (tableau complet 54/31/49/27/38/30, moyenne 38 %,
  pop 1943-2010).
- Round 2 : `logs/campaign_runs/scale4000_scaled_food_20260716_214445.log`
  (**CSV vides — la trace de l'interruption est elle-même la preuve**).

---

## Verdict

**Branche ABANDONNÉE définitivement le 2026-07-22 ; elle ne sera pas reprise.**
L'hypothèse d'échelle est la **limite assumée** de ce travail. Le backlog du
projet repart de poc2.6, **pas** de poc3 (les pistes qui en dépendraient —
HyperNEAT V5, QD/îles à grande pop — sont elles-mêmes des limites assumées, cf.
`10`). L'architecture batchée reste sur la branche `poc3` comme référence
technique, mais **seule l'architecture poc2.x fait foi** pour le reste du projet.
