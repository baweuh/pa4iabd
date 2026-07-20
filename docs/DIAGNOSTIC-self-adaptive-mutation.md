# Mutation auto-adaptative (sigma ES par génome) — diagnostic pré-campagne

**Statut : mécanisme falsifié au diagnostic. Aucune campagne lancée.**
`genome.self_adaptive_mutation` reste `false` par défaut.

Date : 2026-07-20 · branche `poc2.6` · code : commit `5e32408` + `sigma_tau_scale`

## Pourquoi ce levier

Premier levier du projet qui ne touche **ni la sélection ni la
reproduction** : il change *comment* la variation est produite, pas *qui*
se reproduit. Les 11 leviers falsifiés jusqu'ici remodelaient tous la
sélection/repro (fitness sharing, troncature, crossover, génome sparse,
critère minimal, îles, archive de nouveauté, biais, HyperNEAT).

Mécanisme (Schwefel 1981 ; Beyer & Schwefel 2002) : chaque génome porte
son propre pas de mutation `sigma`, muté log-normalement à chaque
reproduction, `sigma' = sigma · exp(tau · N(0,1))` avec `tau = 1/√n`,
`n` = nombre de connexions du génome.

## Méthode

Diagnostic **avant** campagne, délibérément : mesurer si le mécanisme
s'exerce réellement, avant de dépenser 6 seeds × 30k ticks. Deux mesures.

### 1. Déterminisme du chemin legacy (préalable)

Hash bit-à-bit de l'état complet de la population (positions, heading,
énergie, toutes les connexions) après N ticks, code HEAD vs code
pré-commit (`658389b`), `config/default.yaml` :

| seed | ticks | pop | hash |
|---|---|---|---|
| 42 | 800 | 295 | `04974ce8…` — **identique** |
| 123 | 600 | 270 | `69037e61…` — **identique** |

Feature OFF ⇒ aucun `rng` supplémentaire tiré, runs existants inchangés. ✅

### 2. Trajectoire de sigma, tau canonique

`config/lever_self_adaptive_mutation.yaml`, 6000 ticks, 3 seeds :

| seed | sigma médian t=500 → t=6000 | p10–p90 final |
|---|---|---|
| 42 | 0,0500 → **0,0558** | 0,043 – 0,076 |
| 7 | 0,0500 → **0,0510** | 0,042 – 0,064 |
| 123 | 0,0500 → **0,0516** | 0,040 – 0,066 |

Sigma **ne bouge quasiment pas** (+2 % à +12 % sur la médiane).

### 3. Cause : la profondeur de lignée

La dérive log-normale de sigma avance en `tau·√G`, `G` = nombre de
générations traversées par une lignée. Mesure directe (seed 42, compteur
de profondeur parent→enfant sur `_birth`) :

| tick | pop | profondeur médiane | max | reproductions |
|---|---|---|---|---|
| 1000 | 326 | 0 | 4 | 141 |
| 3000 | 400 | 1 | 6 | 332 |
| 6000 | 400 | **3** | 7 | 619 |

**~3 générations en 6k ticks** (≈15–20 extrapolé à une campagne 30k).
Avec `n = 98`, `tau = 0,10` : 15 générations déplacent sigma d'un facteur
~1,5. L'auto-adaptation ES suppose un ordre de grandeur de générations en
plus. **Une campagne à ce réglage aurait mesuré du bruit, pas le levier.**

### 4. Test discriminant : sweep tau

Ajout de `genome.sigma_tau_scale` (multiplicateur sur le tau canonique)
pour donner au mécanisme un budget de dérive réel dans l'horizon
disponible. Seed 42, 6000 ticks :

| tau_scale | sigma médian final | p10 – p90 final |
|---|---|---|
| 1 (canonique) | 0,0558 | 0,043 – 0,076 |
| 3 | **0,0472** | 0,023 – 0,106 |
| 6 | **0,0585** | 0,018 – 0,163 |

Seed 7, tau_scale 3 : médiane finale **0,0497**, p10–p90 0,027 – 0,094.

## Conclusion

Le sweep est le test discriminant du mécanisme :

- **le spread explose** comme prévu (p90/p10 : 1,8 → 4,7 → 9,2) — la
  dérive log-normale fonctionne, l'implémentation est correcte ;
- **la médiane reste collée à la valeur initiale 0,050** dans tous les
  cas, sur les deux seeds.

C'est la signature d'une **dérive pure sans auto-réglage** : la sélection
n'a aucune prise sur sigma. Si sigma était réellement sélectionné, la
médiane convergerait vers une valeur reproductible ≠ 0,050 ; elle ne le
fait pas, elle diffuse symétriquement autour de son point de départ.

Cohérent avec le diagnostic historique du projet (memory
`diagnostics-instrumentation`) : `N_e` ≈ 82–90 sur une population de 400,
soit **sélection ≪ dérive** (poc2.2). L'auto-adaptation ES est un
mécanisme de **second ordre** — sigma n'est sélectionné qu'indirectement,
via le succès des enfants qu'il produit. Un régime où la sélection de
premier ordre est déjà noyée par la dérive ne peut pas transporter un
signal de second ordre.

**Le levier n'est pas « mauvais » : il est structurellement inapplicable
à ce régime.** Falsifié au diagnostic, sans campagne — 12e levier écarté,
et le premier écarté à coût quasi nul.

## Limite honnête de ce diagnostic

Le fourrage n'a **pas** été mesuré. L'hypothèse testée ici est « sigma
s'auto-règle », et elle est falsifiée au niveau mécanistique. Il reste
concevable — non testé — que la seule **hétérogénéité** de sigma (une
population qui mute à des pas variés, sans que la médiane bouge) aide le
fourrage par un autre chemin. Ce serait une hypothèse différente, à poser
explicitement avant d'y dépenser une campagne.

## Code

Conservé, OFF par défaut, 291 tests verts :

- `GenomeConfig.self_adaptive_mutation` / `sigma_min` / `sigma_tau_scale`
- `Genome.sigma` (None quand off), propagé par `clone()`, moyenné par
  `crossover()`, sérialisé seulement s'il existe
- `Genome.mutate_weights()` — mise à jour ES canonique, une fois par appel
- `config/lever_self_adaptive_mutation.yaml`

`sigma_tau_scale` est le seul ajout post-`5e32408` : il existe parce que
le diagnostic l'exigeait, et il documente dans le code pourquoi le tau
canonique ne suffit pas ici.
