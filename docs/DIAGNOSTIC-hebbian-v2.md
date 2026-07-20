# Plasticité Hebbienne V2 (trace d'éligibilité + baseline) — diagnostic partiel

**Statut : implémentée, diagnostic PARTIEL (1 seed), non promue, non falsifiée.**
`hebbian.enabled` reste `false`. Résultats ci-dessous **provisoires**.

Date : 2026-07-20 · branche `poc2.6` · suite de `docs/DIAGNOSTIC-hebbian-v1.md`

## La règle

    e  <- eligibility_decay · e + x·y          (trace, par connexion)
    dw = learning_rate · (m − m̄) · e           (mise à jour contrastive)

Appliquée **chaque tick** (V1 ne l'appliquait que sur capture), `m̄` = moyenne
glissante de la récompense. Corrige les deux défauts diagnostiqués en V1 :
la trace fait porter le crédit sur les ticks d'**approche** et non sur celui
de la capture ; la baseline rend l'apprentissage **contrastif**, donc une
disette peut affaiblir une connexion et la dérive nette sur une vie tend
vers zéro par construction.

Chaque ingrédient est **ablatable indépendamment** en mettant son paramètre
à 0 (`eligibility_decay` → trace du tick courant seulement = V1 ;
`baseline_rate` → `m̄` reste à 0 = pas de baseline).

### Calibrage de la trace — point non trivial

`eligibility_decay = 0,99` (fenêtre ~100 ticks), **pas** le 0,9 habituel.
L'échelle de l'approche est déjà dérivée dans le code :
`diagnostics.capture_lookback_ticks` = ticks pour traverser la portée
sensorielle à `max_speed` = **134** sous `default.yaml`. Une fenêtre de 0,9
couvrirait ~10 ticks, soit moins d'un dixième d'une approche. Le codebase
avait déjà été mordu par ce genre de constante temporelle silencieusement
décalibrée (l'ancien `lookback=30` fixe, cassé quand `max_speed` a été
divisé par 2 en poc2.4).

## Résultats — sweep `learning_rate`, seed 42, 6000 ticks

Valeurs à t=6000. Témoin = run sans plasticité, même seed.

| réglage | steer_inné | steer_appris | pop |
|---|---|---|---|
| **témoin (sans plasticité)** | **0,359** | 0,359 | 400 |
| V1 lr=0,01 | 0,345 | 0,345 | 400 |
| V1 lr=0,1 | 0,138 | 0,109 | 400 |
| **V2** lr=0,01 | 0,229 | 0,220 | 400 |
| **V2** lr=0,03 | 0,165 | 0,158 | 400 |
| **V2** lr=0,1 | 0,061 | 0,034 | 400 |

### Ce qui est corrigé — le mode d'échec n°1

En V1, `steer_appris` < `steer_inné` **systématiquement** : l'agent
apprenait contre son propre fourrage. En V2 l'écart change de signe selon
les relevés, et l'apprentissage est parfois **bénéfique** :

| relevé | inné | appris | écart |
|---|---|---|---|
| lr=0,01 t=3000 | 0,116 | 0,140 | **+0,024** |
| lr=0,1 t=4000 | 0,069 | 0,103 | **+0,034** |
| lr=0,1 t=5000 | 0,052 | 0,085 | **+0,033** |
| lr=0,01 t=6000 | 0,229 | 0,220 | −0,009 |

Plus de dégradation systématique. La trace + baseline font bien ce pour quoi
elles ont été ajoutées.

### Ce qui n'est PAS corrigé — le mode d'échec n°2

`steer_inné` reste **très en dessous du témoin à tous les réglages**, et
décroît monotonement avec `lr` : 0,229 / 0,165 / 0,061 contre **0,359**.
La plasticité continue donc de **handicaper l'évolution elle-même**, ce qui
était le résultat le plus dommageable de V1 et le reste.

Pire, à `lr` égal V2 nuit **plus** que V1 (0,229 vs 0,345 à lr=0,01) — ce
qui est cohérent : V2 met à jour à chaque tick et la trace accumule, donc la
perturbation effective à `lr` donné est bien plus grande. Les `lr` de V1 et
V2 ne sont pas comparables directement.

## Limites — à lire avant de conclure quoi que ce soit

- **Un seul seed (42), un seul run par réglage.** Aucune réplication.
- `steer_inné` est **bruité d'un relevé à l'autre** : le témoin lui-même fait
  0,124 → 0,146 → 0,249 → 0,223 → 0,296 → 0,359. Un écart mesuré à un seul
  point de temps sur un seul seed ne vaut pas conclusion.
- Le sweep n'a pas été poussé sous `lr = 0,01`, alors que la monotonie
  suggère que l'optimum éventuel est **en dessous** de la plage testée.
- **Les ablations n'ont pas été lancées** (trace seule / baseline seule),
  alors que le code les rend triviales. Elles diraient lequel des deux
  ingrédients porte l'amélioration du mode 1.

**Rien n'est falsifié ni promu ici.** Le signal honnête est : V2 corrige le
défaut individuel, ne corrige pas le défaut évolutif, et demande des seeds
pour trancher.

## Coût

Mesuré : **47 → 30 ticks/s (−37%)** à population comparable. La mise à jour
est désormais par tick et par connexion (~98 × 400 agents), là où V1 ne
touchait les poids que ~3 fois par vie. À intégrer au budget de toute
campagne V2.

## Suite proposée

1. **Ablations** (trace seule vs baseline seule) — bon marché, déjà câblées.
2. **Sweep vers le bas** (`lr` = 0,001 / 0,003), la monotonie l'indique.
3. Si un réglage rapproche `steer_inné` du témoin **et** garde l'écart
   appris−inné positif : campagne 6 seeds. Sinon, conclure comme V1 en
   documentant que le mode 2 est le vrai obstacle.

Hypothèse à garder en tête pour le mode 2 : le bruit phénotypique de
l'apprentissage masque les différences génétiques (« hiding », inverse de
l'effet Baldwin), et dans un régime où `N_e` ≈ 85 la sélection n'a pas la
marge pour l'absorber. Si c'est bien ça, **aucun réglage de la règle ne
sauvera le levier** — ce serait la même conclusion structurelle que pour la
mutation auto-adaptative, et l'ablation `learning_rate → 0` le dirait.

## Code

OFF par défaut, 318 tests verts (7 nouveaux propres à V2), chemin legacy
bit-à-bit inchangé (mêmes hashes : seed 42/800 `04974ce8…`, seed 123/600
`69037e61…`).

- `HebbianConfig.eligibility_decay` / `baseline_rate`
- `NeuralNetwork._trace` / `_reward_baseline`, `apply_hebbian()` réécrite
- `Agent.eat()` appelle désormais `apply_hebbian` à **chaque** tick
- `config/lever_hebbian.yaml` (V2)

⚠️ Piège rencontré : après le passage V1→V2 **les tests V1 passaient tous
inchangés**, parce que V2 se réduit exactement à V1 au premier appel (trace
vide, baseline nulle). Ils ne testaient donc plus rien de distinctif. Ils ont
été corrigés et 7 tests spécifiques V2 ajoutés (trace qui reporte le crédit
d'un tick antérieur, ablations à 0, décroissance de la trace, baseline qui
converge, tick sec qui *inverse* la mise à jour, dérive bornée sur une vie).
