# Plasticité Hebbienne modulée par récompense — V1, diagnostic pré-campagne

**Statut : règle V1 falsifiée au diagnostic. Aucune campagne lancée.**
`hebbian.enabled` reste `false` par défaut.

> ⚠️ **Ce document décrit l'état au 2026-07-20 et sa « suite proposée » a depuis
> été implémentée ET falsifiée.** Ne pas le lire comme un chantier ouvert :
> V2 (trace + baseline) a bien corrigé les deux défauts identifiés ici — les
> ablations le prouvent — et a **échoué quand même**, l'apprentissage restant un
> pile ou face (41-55 % de gagnants, 7 réglages × 2 seeds). Le chantier est CLOS.
> Conséquence directe sur la conclusion ci-dessous (« falsification de la règle,
> pas du concept ») : elle était juste à la date de ce document, mais **c'est
> désormais le concept lui-même qui est falsifié sur CETTE tâche** — voir la
> note en fin de section. Résultat complet : `docs/DIAGNOSTIC-hebbian-v2.md`.

Date : 2026-07-20 · branche `poc2.6` · règle choisie avec Robin (option A)

## Le levier

Deuxième levier hors sélection/reproduction, et le **premier mécanisme du
projet où le comportement d'un agent change pendant sa propre vie** au lieu
de ne changer qu'entre générations.

    dw = learning_rate · m · x · y        (m = pommes mangées au tick)

Reward-gated : rien ne bouge sur un tick sans capture. Non-lamarckien : les
poids appris vivent dans le réseau compilé, jamais dans le génome.

Délibérément **de premier ordre** — `learning_rate` est une constante YAML,
aucun paramètre de règle n'est évolué. C'est la leçon directe de
`docs/DIAGNOSTIC-self-adaptive-mutation.md` : ce régime (`N_e` ≈ 82-90 sur
pop 400) ne peut pas porter un signal de second ordre. La plasticité échappe
à ce piège parce que les poids appris changent le fourrage **du porteur**.

## Précautions de mesure (sans lesquelles le résultat serait faux)

Deux pièges identifiés et traités avant de mesurer quoi que ce soit :

1. **`steer_score` et `behavior_descriptor` étaient mis en cache à vie**, au
   motif explicite que « le réseau est gelé ». La plasticité casse cette
   hypothèse. Non corrigé, `steer_score` — la métrique-titre des campagnes —
   aurait mesuré le réseau **inné** et rapporté **exactement zéro effet**
   pour un levier dont toute la thèse est que le comportement change pendant
   la vie. Falsification faussement positive garantie. Les deux caches sont
   maintenant contournés sous `hebbian.enabled`.
2. **La mise à jour ne vit PAS dans `NeuralNetwork.activate()`** mais dans
   `apply_hebbian()`, appelé seulement par `Agent.eat()`. `steer_score`, le
   descripteur de nouveauté et les requêtes CPPN HyperNEAT appellent tous
   `activate()` pour **observer** — mesurer un agent ne doit pas modifier son
   cerveau. Test dédié : `test_activate_alone_never_changes_weights`.

Contrôle de validité : run témoin `hebbian.enabled=false`, écart
inné↔appris = **0,0000 exactement** à chaque relevé. Et le chemin legacy
reste bit-à-bit identique (mêmes hashes que le diagnostic sigma : seed
42/800 ticks `04974ce8…`, seed 123/600 ticks `69037e61…`).

## Résultats — sweep `learning_rate`, seed 42, 6000 ticks

`steer_inné` = réseau reconstruit depuis le génome ; `steer_appris` = réseau
réellement porté par l'agent après apprentissage.

| réglage | steer_inné t=6000 | steer_appris | pommes/vie p90 | pop |
|---|---|---|---|---|
| **sans plasticité** (témoin) | **0,359** | 0,359 | 13 | 400 |
| lr = 0,01 | 0,345 | 0,345 | 12 | 400 |
| lr = 0,1 | 0,138 | **0,109** | 7 | 400 |
| lr = 0,3 | 0,030 | 0,050 | 3 | **99** |

À `lr = 0,01` le mécanisme ne s'exerce quasiment pas : un agent médian ne
mange que **3 pommes dans toute sa vie**, donc ne reçoit que 3 mises à jour,
et l'écart inné↔appris plafonne à 0,003. C'est l'exact analogue du budget
générationnel qui avait tué la mutation auto-adaptative — ici le budget est
le **nombre d'événements de récompense par vie**, et il est minuscule.

Monter `lr` fait bien s'exercer le mécanisme (écart inné↔appris 0,08–0,12),
et révèle **deux modes d'échec distincts**.

### Mode 1 — l'apprentissage dégrade la politique de l'individu

`steer_appris` < `steer_inné` systématiquement. Seed 7 à lr = 0,1, les 5
relevés successifs : −0,010, −0,016, −0,009, −0,025, −0,028. Cohérent sur
les deux seeds, jamais dans l'autre sens. L'agent apprend **contre** son
propre fourrage.

### Mode 2 — la plasticité handicape l'évolution elle-même

Le plus intéressant : `steer_inné` lui-même s'effondre, **0,359 → 0,138**.
Ce ne sont pas les mêmes génomes qui sont sélectionnés. C'est l'**inverse de
l'effet Baldwin** : le bruit d'apprentissage masque les différences
génétiques, la sélection distingue moins bien les bons génomes (effet
« hiding » documenté dans la littérature Baldwin). Dans un régime où la
sélection est déjà noyée par la dérive (`N_e` ≈ 85), ajouter du bruit
phénotypique est directement nuisible.

## Diagnostic mécaniste — pourquoi cette règle-là ne pouvait pas marcher

La règle implémentée est du **renforcement positif pur, sans baseline ni
trace d'éligibilité**. Deux défauts, tous deux structurels :

1. **Le mauvais instant est renforcé.** `x · y` est pris au tick de la
   capture — or à ce tick l'agent est *sur* la pomme, capteur saturé, et la
   pomme disparaît juste après. L'état renforcé est « une pomme est collée à
   moi », pas la phase d'**approche à distance**, qui est la seule partie
   utile de la politique de fourrage.
2. **Pas de baseline.** Sans terme de contraste `(m − m̄)`, *toute* connexion
   active pendant une capture est renforcée, causale ou non. Le résultat net
   est une dérive positive corrélée à l'activité générale → saturation des
   tanh → réponse aplatie, ce que `steer_score` mesure exactement.

Ce sont précisément les deux ingrédients que Soltoggio et al. conservent et
que cette simplification a jetés. **C'est donc une falsification de CETTE
RÈGLE, pas du concept de plasticité.** La distinction est réelle et il faut
la tenir : contrairement à la mutation auto-adaptative — écartée pour une
raison *structurelle* (un mécanisme de second ordre est impossible à
`N_e` ≈ 85, aucun réglage n'y change rien) — rien ici n'interdit *a priori*
à une règle mieux construite de fonctionner.

> **Mise à jour 2026-07-21 — cette distinction n'a pas survécu.** V2 est
> précisément « la règle mieux construite » : elle rétablit les deux ingrédients
> jetés ici, et les ablations confirment que chacun fait son travail (la trace
> fournit l'amplitude, la baseline borne la dérive). Elle échoue néanmoins. La
> raison rejoint finalement celle de la mutation auto-adaptative : la trace couvre
> ~100 ticks pour ~3 récompenses par vie, donc l'attribution de crédit est du
> bruit — un fait sur la **parcimonie de la tâche**, qu'aucune forme de règle ne
> change. La plasticité Hebbienne est donc écartée pour une raison structurelle
> elle aussi, simplement découverte un cran plus tard.

## Suite proposée — V2 : trace d'éligibilité + baseline  *(depuis IMPLÉMENTÉE puis FALSIFIÉE)*

Correction exactement ciblée sur les deux défauts diagnostiqués :

    e ← decay · e + x · y                     (trace, par connexion)
    dw = learning_rate · (m − m̄) · e          (m̄ = récompense moyenne glissante)

La trace fait porter le crédit sur les ticks d'**approche** et pas seulement
sur celui de la capture (défaut 1) ; la baseline `(m − m̄)` rend
l'apprentissage **contrastif** — une capture ordinaire ne renforce rien, seul
un écart à l'attendu le fait, et une disette peut *affaiblir* (défaut 2).
C'est la forme canonique R-STDP / Hebbien neuromodulé de la source.

Coût : contenu en implémentation, mais **−37 % de perf mesurés** une fois
livrée (47 → 30 ticks/s : la mise à jour devient par tick et par connexion).

~~Non engagé~~ — **engagé le 2026-07-20** (commit `aa19ae7`), diagnostiqué et
falsifié le 2026-07-21 (commit `1001faf`). Voir `docs/DIAGNOSTIC-hebbian-v2.md`.

À noter pour V2 : le budget de récompense (~3 pommes/vie médian) reste la
contrainte dure, et il **n'est pas modifiable** sans changer la tâche. Toute
règle qui exige beaucoup d'événements pour converger est hors-jeu ici, quel
que soit son mérite théorique.

## Code

Conservé, OFF par défaut, 311 tests verts (20 nouveaux) :

- `HebbianConfig` (`enabled` / `learning_rate` / `weight_max`), section YAML
  optionnelle comme `novelty` / `hyperneat`
- `NeuralNetwork.apply_hebbian()` + enregistrement conditionnel des
  activations (coût nul quand off)
- `Agent.eat()` déclenche l'apprentissage ; `_plastic` contourne les deux
  caches de mesure
- `config/lever_hebbian.yaml`
