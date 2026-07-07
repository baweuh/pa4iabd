# Audit poc2.2 — v3 : les métriques, la perf réelle des agents, et ce qui nous manque

> Prolonge `AUDIT-poc2.2-v2.md`. La v2 a été écrite **avant** le commit `dc20330`
> (« 5 améliorations architecturales : B3a égocentrique / B3b fécondité∝énergie /
> élitisme / input 2D / I2 clamp »), qui a implémenté précisément ce que la v2
> mettait en backlog. **Question centrale de cette v3 : ces 5 correctifs ont-ils
> débloqué l'évolution ?** Réponse, preuves à l'appui : **ils ont réglé la
> viabilité, mais pas l'adaptation.** La population survit désormais 24 000 ticks
> sans s'éteindre — mais elle n'apprend toujours *rien* à fourrager.

---

## Verdict en une phrase

Le meilleur agent produit par 24 000 ticks d'évolution est un **perceptron
49→2 sans neurone caché, aux poids quasi aléatoires, qui s'oriente légèrement *à
l'opposé* des pommes** (r = −0,17) et se fait battre par 143 nouveau-nés
aléatoires sur 200. Il n'y a **aucune adaptation du fourragement** : `record_apples`
est une loterie longévité+chance, pas une mesure de compétence. Le blocage n'est
pas (plus) la viabilité ni le repère de sortie — c'est la **dynamique
évolutive** : la pression de sélection sur le fourragement est très inférieure au
bruit de mutation et à la dérive, donc la compétence ne s'accumule ni ne se
transmet.

---

## ÉTAPE 0 — La preuve empirique (run `logs/2026-06-12_140936`, seed 42, 24 000 ticks)

C'est le run le plus long et le plus récent, produit avec la config actuelle
(post-`dc20330`). Trajectoire :

| tick   | pop | food/80 | record_apples | avg_lifespan | max_gen | mean_gen | net_size | genetic_dist | mean_forage |
|--------|-----|---------|---------------|--------------|---------|----------|----------|--------------|-------------|
| 100    | 174 | 43      | 2             | 81           | 5       | 0.60     | 149.03   | 0.39         | 0.00282     |
| 500    | 200 | 32      | 6             | 445          | 5       | 0.86     | 149.05   | 0.46         | 0.00158     |
| 2 500  | 200 | 35      | 17            | 2 198        | 5       | 1.03     | 149.13   | 0.58         | 0.00164     |
| 5 100  | 200 | 19      | **27**        | 1 452        | 8       | 3.52     | 149.15   | 0.84         | 0.00279     |
| 10 000 | 200 | 11      | 27            | 2 451        | 10      | 5.70     | 149.15   | 1.31         | 0.00175     |
| 15 000 | 200 | 14      | 27            | 2 570        | 12      | 7.26     | 149.49   | 2.15         | 0.00184     |
| 20 000 | 200 | 15      | 27            | 2 704        | 13      | 8.97     | 149.52   | 2.59         | 0.00177     |
| 23 900 | 200 | 21      | 27            | 2 760        | 14      | 10.56    | 149.53   | 2.66         | 0.00218     |

**Ce qui a changé (vs v2) — la viabilité est réglée :**
- ✅ **Plus d'extinction.** La population atteint le plafond (200) au tick ~200 et
  y reste **24 000 ticks**. En v2, extinction au tick 5 100 (défaut v1) à 9 500 (E1).
  Élitisme + reproduction bon marché + contrôle égocentrique ont supprimé la
  spirale de mort.
- ✅ **Profondeur générationnelle.** `max_generation` 5→14, `mean_generation`→10,6.
  Vraies lignées multi-générationnelles.
- ✅ **Diversité préservée.** `mean_genetic_distance` 0,39→2,66 (monotone).

**Ce qui n'a PAS changé — l'adaptation reste nulle :**
- ❌ **`record_apples` gelé à 27** depuis le tick 5 100 : **18 800 ticks sans être
  battu**.
- ❌ **`mean_forage_rate` sans tendance** : oscille dans 0,0017–0,0025 tout le run,
  aucune montée directionnelle.
- ❌ **`avg_network_size` gelé à ~149** (+0,5 sur 24 000 ticks) = topologie du
  fondateur. La **complexification NEAT ne s'est jamais enclenchée**.
- ❌ La montée de `mean_genetic_distance` avec un fourragement plat = **signature de
  dérive neutre**, pas de divergence adaptative.

**Note de lecture — les « vagues » tous les 5 000 ticks.** `avg_lifespan` s'effondre
à chaque multiple de `max_age` (5 000) : ticks 5 000, 10 000, 15 000, 20 000. C'est
la cohorte fondatrice + descendants qui atteignent l'âge limite **simultanément**.
Autrement dit, **une grande partie de la population meurt de vieillesse, pas de
faim** — indice direct que la survie ne trie presque pas sur la compétence
(voir Cause 1).

---

## ÉTAPE 1 — La preuve décisive : sonde comportementale du champion

Le CSV ne peut pas dire *pourquoi* `record_apples` plafonne. Deux hypothèses :
(a) le champion est un bon fourrageur mais la chance limite le record, ou
(b) le « champion » n'a aucune compétence et 27 n'est que longévité+hasard.
On tranche en **regardant le contrôleur lui-même**.

**Topologie du champion** (`best_genome.json`, record 27) :

```
nodes : 49 input, 2 output, 0 hidden
connections : 98 (toutes activées) — IDENTIQUE au génome fondateur
poids : min −1,39  max +1,64  moyenne −0,04  écart-type 0,70
        (init = uniforme ±1, écart-type 0,58 → poids quasi inchangés)
0 poids proche du clamp ±5
```

Le meilleur fourrageur de 24 000 ticks est **topologiquement un nouveau-né**, aux
poids à peine perturbés au-delà du tirage initial.

**Sonde comportementale.** On place une pomme seule sur le rayon *k* (proche),
tous autres capteurs neutres, et on mesure le signe du virage. Un vrai fourrageur
tourne *vers* la pomme : corrélation de Pearson entre « pomme à gauche » et
« tourne à gauche ». Score 1,0 = fourrageur parfait ; 0,0 = ignore les pommes ;
négatif = anti-fourrageur.

| Contrôleur | Score d'orientation-pomme |
|------------|----------------------------|
| **Champion (record 27)** | **r = −0,173** (tourne légèrement *à l'opposé*) |
| Nouveau-nés aléatoires (n=200) | moyenne r = +0,008 · plage [−0,62, +0,67] |
| **Percentile du champion dans le pool aléatoire** | **28ᵉ** |
| **Nouveau-nés aléatoires meilleurs que le champion** | **143 / 200** |

**Conclusion sans appel.** L'évolution n'a pas seulement échoué à *améliorer* le
fourragement — le champion est **en dessous du hasard**. Ses 27 pommes viennent
d'avoir vécu longtemps dans un monde où 15–30 pommes sont visibles en
permanence : un marcheur quasi-aléatoire en percute ~27 sur une vie de 5 000
ticks. **Rien n'a été appris.** L'hypothèse (b) est confirmée.

---

## ÉTAPE 2 — Audit paramètres & architecture : *pourquoi* rien n'évolue

La mécanique du code est correcte (égocentrisme bien implémenté, DFS anti-cycle
fiable, tri topo caché, déterminisme). Le problème est dans la **dynamique**, à
l'intersection des paramètres et de l'architecture. Quatre causes, classées par
impact.

### 🔴 Cause 1 — Le différentiel de sélection sur le fourragement est minuscule

Pour que « mieux fourrager » se traduise en « plus de descendants », il faut que
la survie **ou** la reproduction dépendent fortement de la compétence. Ni l'une
ni l'autre ici.

**La survie est quasi gratuite.**
- `energy_drain_per_tick = 0.0004` → un agent qui **ne mange rien** survit
  `1.0 / 0.0004 = 2 500 ticks` = **50 % de `max_age`**.
- Pour atteindre la vieillesse (5 000 ticks) il suffit de manger **2 pommes sur
  toute la vie** (drain total 2,0 − énergie initiale 1,0 = 1,0 = 2 pommes).
- Résultat : la quasi-totalité des agents meurent de **vieillesse**, pas de faim
  (cf. vagues de mortalité tous les 5 000 ticks). La famine ne trie presque
  personne → **pas de sélection sur la survie**.

**Le gradient de reproduction est écrasé par le plafond d'énergie.**
- `max_energy = 2.0`, `reproduction_threshold = 1.1`, `reproduction_cost = 0.35`.
- La fécondité∝énergie (B3b, boucle `while can_reproduce()`) ne peut produire que
  **1 à 3** descendants par salve : un agent à 2,0 fait 3 enfants
  (2,0→1,65→1,30→0,95), un agent à 1,1 en fait 1. Le plafond 2,0 est **juste
  au-dessus** du seuil 1,1 → dynamique quasi nulle.
- Un fourrageur 10× meilleur **ne peut pas** laisser 10× plus de descendants : il
  est plafonné à ~3× *et* bridé par les places libres (population au plafond).

**Bilan Cause 1 :** le coefficient de sélection *s* sur le fourragement est petit.
Le meilleur agent jamais trouvé (27 pommes/vie ≈ 0,0054 pomme/tick) n'est que
~2,5× la moyenne (0,002) — un écart de fitness étroit, là où un système qui évolue
vraiment montrerait des champions 10–100× au-dessus de la moyenne et croissants.

### 🔴 Cause 2 — La charge de mutation détruit l'héritabilité (la dérive noie la sélection)

À chaque naissance, `mutate_weights` perturbe **80 %** des ~98 connexions par un
bruit gaussien σ=0,2 :
- Déplacement RMS du vecteur de poids **par génération** :
  `√(98 × 0,8 × 0,2²) ≈ 1,77`.
- Les poids utiles sont d'ordre O(1) (init ±1, écart-type 0,58). **Chaque
  génération, le vecteur de poids bouge d'à peu près sa propre magnitude.**

Autrement dit, même si un bon contrôleur naît, ses enfants sont **re-randomisés** :
la compétence n'est pas transmissible. Avec un *s* petit (Cause 1) et une variance
mutationnelle énorme (Cause 2), la réponse à la sélection par génération
(équation de l'éleveur, Δ ≈ h²·S) est ≈ 0. **La population dérive.** Preuve directe :
`mean_genetic_distance` monte tout droit (0,39→2,66) pendant que la compétence
reste au niveau du hasard — c'est *la* signature d'une marche aléatoire dans
l'espace des génomes.

### 🔴 Cause 3 — La complexification NEAT ne s'enclenche jamais

- Le génome fondateur est **déjà complètement connecté** (49→2). Donc
  `add_connection` est un **no-op** tant qu'aucun neurone caché n'existe (toutes
  les arêtes entrée→sortie existent déjà ; `_is_valid_edge` renvoie False).
- `add_node` tire à 3 %/naissance, mais avec sélection faible (Cause 1) + forte
  mutation de poids (Cause 2) + `remove_node` (1 %), un neurone caché ne se fixe
  ni ne se propage.
- Preuve : `avg_network_size` gelé à 149 (= fondateur), champion à **0 caché**. La
  moitié « augmenting topologies » de NEAT est **inerte** ; on évolue de fait un
  perceptron mono-couche à topologie fixe — et même ça ne converge pas, faute de
  Causes 1–2.

### 🟡 Cause 4 (mesure) — `mean_forage_rate` ne *peut pas* monter au plafond de charge

- Offre de nourriture : `80 pommes / 150 ticks de respawn ≈ 0,53 pomme/tick`,
  partagée par ~200 agents → **plafond dur de ~0,00267 pomme/agent/tick** sur la
  moyenne, *quelle que soit la compétence*.
- Observé : `mean_forage_rate ≈ 0,0020` (≈ 75 % du plafond). La marge de montée
  est donc faible (~33 %) *et* elle ne monte pas.
- Conséquence méthodologique : au plafond démographique, la métrique que la v2
  désignait comme « LE signal d'amélioration » est **structurellement bridée**. Le
  signal de compétence non plafonné par l'offre serait `record_apples`,
  `max_forage_rate` ou le score d'orientation — **tous plats/aléatoires**. La
  conclusion « pas d'adaptation » tient donc doublement.

### Notes architecturales secondaires

- 🟡 **Pas de biais** dans le réseau (`network.py` : sortie = Σ w·x, caché =
  tanh(Σ w·x), aucun nœud de biais). Un perceptron sans biais ne peut pas fixer
  une action par défaut indépendante des entrées ; le canal distance (toujours
  ~1,0) sert de pseudo-biais mais reste couplé à la perception. Bride légèrement
  même un bon perceptron.
- 🟢 **Élitisme dormant 80 % du run.** L'injection d'élite ne se déclenche qu'à un
  nouveau record ; record gelé à 27 depuis le tick 5 100 → **aucune ré-injection
  pendant 18 800 ticks**. Sur la majorité du run, c'est de la dérive pure.

---

## ÉTAPE 3 — Ce qui nous manque (leviers, classés par effet de levier)

**Le diagnostic clé, contre-intuitif vs v2 :** la v2 concluait que le plafond était
*architectural* (memoryless + repère absolu) et misait sur l'égocentrisme (B3a)
comme levier. B3a a été livré — **et l'adaptation est toujours nulle**. Donc le
repère de sortie n'était **pas** la contrainte liante. La contrainte liante est le
**rapport sélection / (mutation + dérive)**. Il faut le remonter au-dessus de 1.
Approche recommandée : **une expérience = un bouton**, sur seed 42, 12–20 k ticks,
en lisant le **score d'orientation-pomme** (sonde ci-dessus) et `record_apples`,
pas seulement `mean_forage_rate`.

| # | Levier | Bouton concret | Pourquoi (cause visée) |
|---|--------|----------------|------------------------|
| **1** | 🔴 **Réduire la charge de mutation** | `weight_mutation_rate 0.8→~0.15` et/ou `weight_perturbation 0.2→~0.05` | Cause 2. Sans héritabilité, aucune sélection ne s'accumule. **Le bouton au plus fort levier** : rend un bon contrôleur transmissible. |
| **2** | 🔴 **Rendre la survie dépendante de la compétence** | ↑ `energy_drain_per_tick` (ex. 0.0004→0.0015) et/ou ↓ `max_age` | Cause 1. Fait mourir de faim les mauvais fourrageurs *avant* la vieillesse → vrai différentiel de survie. |
| **3** | 🔴 **Élargir le gradient de reproduction** | ↑ `max_energy` (ex. 2.0→5–8) pour que les bons fourrageurs thésaurisent et surpassent en descendance ; ou lier la fécondité au **débit d'énergie cumulé**, pas à l'énergie instantanée plafonnée | Cause 1. Un fourrageur 5× meilleur doit laisser ~5× plus de descendants. |
| **4** | 🟡 **Débloquer la complexification** | Démarrer **minimal** (pas tout-connecté) pour que `add_connection` serve ; ajouter un **nœud de biais** | Cause 3 + note biais. Donne à NEAT sa raison d'être et de l'expressivité. |
| **5** | 🟡 **Corriger le yardstick** | Métrique de compétence non bridée par l'offre : score d'orientation-pomme moyen de la population, ou sonde périodique « 1 agent seul dans un champ de pommes fixe → temps de capture » | Cause 4. Rend l'adaptation observable même au plafond démographique. |

**Ordre d'attaque conseillé :** 1 puis 2+3 ensemble (elles se renforcent :
sélection plus forte *et* héritabilité), en instrumentant avec 5. Le levier 4
(architecture NEAT) ne portera ses fruits qu'une fois 1–3 en place — sinon la
structure ajoutée dérive comme le reste.

**Ce qu'il ne faut PAS refaire :** un énième réglage de `reproduction_threshold`/
`reproduction_cost` (déjà exploré E0/E1/E2 en v2) — ça déplace la démographie, pas
l'adaptation. Le problème n'est pas *combien* d'agents vivent, c'est que la
sélection est trop faible et la mutation trop forte pour que la compétence monte.

---

## Annexe — Chiffres clés (tous vérifiés sur le run 24 k et le code)

```
Charge de mutation      : ~78/98 poids perturbés par naissance ; RMS 1,77/génération
Plafond offre-nourriture: 80/150 = 0,533 pomme/tick ÷ 200 = 0,00267/agent/tick
Survie « gratuite »     : lifespan sans manger = 2 500 ticks (50 % de max_age)
                          vieillesse atteinte en mangeant 2 pommes / vie
Champion (record 27)    : 49→2, 0 caché, 98 conn, poids σ=0,70 (≈ init)
Score orientation-pomme : champion r=−0,173 ; 28ᵉ percentile ; 143/200 aléatoires meilleurs
record_apples           : 2→27 au tick 5 100, gelé 18 800 ticks
avg_network_size        : 149,03→149,53 (complexification négligeable)
mean_genetic_distance   : 0,39→2,66 (dérive monotone)
```

## Méthode

- Données : `logs/2026-06-12_140936/metrics.csv` (24 000 ticks, seed 42, config
  actuelle) + `best_genome.json` du même run.
- Sonde comportementale : reconstruction du réseau du champion via `NeuralNetwork`,
  stimulus contrôlé (pomme unique par rayon), comparée à 200 génomes fondateurs
  aléatoires. Déterministe (seed fixe).
- Code lu : `agent.py`, `simulation.py`, `genome.py`, `network.py`, `config.py`,
  `config/default.yaml`.

---

## ÉTAPE 5 — Expériences leviers (2026-07-06) : ce que valent réellement les correctifs

Test empirique des leviers proposés à l'ÉTAPE 3, **mesurés au niveau population**
(steering moyen des ~200 agents vivants via `tools/run_and_probe.py`, pas le seul
champion qui est trop bruité). Seeds multiples pour éviter le piège single-seed.

**Métrique** : score d'orientation-pomme moyen de la population + % d'agents à
r > 0,1 (fourrage dirigé). Runs 15 000 ticks (sauf indication).

| Config | seed 42 | seed 7 | seed 123 | Lecture |
|--------|---------|--------|----------|---------|
| **Baseline** (défaut, 24k) | ~0 % | — | — | anti-fourrageur (r=−0,17) |
| **L1** — mutation ↓ (0,15/0,05) | −0,12 / 9 % | — | — | héritabilité seule ⇒ **aucune adaptation** |
| **L1+L2** — + drain 0,0015 | **+0,36 / 99 %** | −0,23 / 14 % | +0,09 / 43 % | fourrage fort MAIS **seed-dépendant** |
| **L1+L2** — 30 000 ticks | +0,39 / 100 % | **−0,30 / 0 %** | +0,11 / 54 % | durée ⇒ seed 7 se **verrouille pire** |
| **L1+L2+L3** — + max_energy 5,0 | +0,26 / 86 % | — | — | **L3 dilue** (portées mutées = dérive) |
| **A** — mutation intermédiaire 0,35/0,12 | +0,18 / 70 % | −0,16 / 8 % | +0,13 / 60 % | variance ↓ mais plafond ↓, seed 7 non sauvé |
| **B** — nourriture rare (count 40) | −0,26 / 0 % | +0,13 / 93 % | −0,37 / 0 % | **rebrasse** les seeds, pas plus robuste |

### Conclusions expérimentales

1. **Deux conditions nécessaires, aucune suffisante.** L1 (héritabilité) seul laisse
   la population anti-fourrageuse (9 %). C'est L2 (famine sélective, `drain` ×3,75
   → population *food-limited*) qui crée la pression — mais seulement transmissible
   grâce à L1. **L1+L2 ensemble** produit du fourrage fort (seed 42 : 99 %). Cela
   valide la thèse de la v3 : il fallait remonter le rapport sélection/(mutation+
   dérive) sur *les deux* termes.

2. **L3 (max_energy 5,0) est à écarter.** La fécondité∝énergie avec plafond haut
   laisse un agent chanceux inonder la population d'une portée mutée = amplificateur
   de dérive. Steering ↓ (99 %→86 %), diversité génétique explose (0,7→5,6).

3. **Blocage résiduel : convergence prématurée seed-dépendante.** L1+L2 n'est **pas
   robuste** : selon le seed, la population se verrouille dans le bassin fourrageur
   (42) ou anti-fourrageur (7). Mutation basse = préserve les gains MAIS aussi les
   malchances fondatrices. Allonger la durée aggrave (fixation). Ni la mutation
   intermédiaire (A) ni la nourriture rare (B) ne rendent le fourrage robuste sur
   les 3 seeds — elles rebrassent seulement quelle graine gagne.

4. **Cause profonde du non-déterminisme.** Le fourrage *dirigé* n'est pas
   *nécessaire* pour survivre : à pop 200 food-limited, l'encounter aléatoire suffit
   (seed 7 maintient 200 anti-fourrageurs vivants). La sélection sur le *steering*
   est donc faible et dominée par la dérive fondatrice. Remedy B (nourriture rare)
   fait justement fourrager seed 7 (93 %) en rendant l'encounter aléatoire
   insuffisant — mais déstabilise les autres. Le signal est clair : **il faut rendre
   le fourrage dirigé payant/nécessaire, via un changement de mécanisme, pas de
   paramètre.**

### Pistes mécanisme (au-delà du réglage de paramètres) — pour la suite

- **Coût de déplacement** (énergie ∝ vitesse/tick) : l'errance aléatoire devient
  chère → le fourrage efficace dirigé est directement récompensé. Cible la cause 4.
- **Reproduction liée aux pommes cumulées** (pas à l'énergie instantanée) : couple
  la fécondité à la compétence de fourrage mesurée sur la vie.
- **Maintien de diversité** (fitness sharing / niching NEAT) : empêche le
  verrouillage fondateur → réduit la variance inter-seed.
- **Population plus grande** : réduit la dérive fondatrice (au prix du CPU).

**État net (2026-07-06)** : l'émergence du fourrage est **démontrée possible**
(seed 42 : 99 %) et le duo L1+L2 est la base directionnelle correcte, mais la
**robustesse inter-seed reste non résolue** au niveau paramétrique. La prochaine
avancée demande un changement de mécanisme (coût de déplacement en tête).

---

## ÉTAPE 6 — Coût de déplacement + méta-conclusion sur la robustesse (2026-07-06)

Suite au choix « coût de déplacement » (Levier mécanisme). Implémenté : nouveau
param `agent.move_cost` (énergie/tick ∝ |vitesse avant|), défaut 0.0 (comportement
legacy inchangé, 141 tests verts). Chargé dans `Agent.metabolize`. But : rendre
l'errance aléatoire coûteuse pour que le fourrage dirigé efficace soit sélectionné.

**Résultats (sur L1+L2, 3 seeds, 15k ticks) :**

| move_cost | seed 42 | seed 7 | seed 123 | pop |
|-----------|---------|--------|----------|-----|
| **0.0003** (lo) | −0,09 / **0 %** | −0,33 / 0 % | +0,05 / 11 % | 135–157 |
| **0.0006** (hi) | +0,36 / **100 %** | −0,18 / **0 %** | +0,09 / 46 % | 62–90 |

Le coût de déplacement **ne robustifie pas** : seed 7 reste à 0 % sous les deux
valeurs ; à 0.0003 il déstabilise même seed 42 (99 %→0 %). Comme les autres, il
**rebrasse** l'issue au lieu de la fiabiliser.

### Méta-conclusion (après 7 configs testées)

Récapitulatif de tout ce qui a été essayé pour robustifier le fourrage :
mutation (0.15 / 0.35 / 0.8), drain (0.0004 / 0.0015), max_energy (2.0 / 5.0),
densité de nourriture (40 / 80), coût de déplacement (0 / 0.0003 / 0.0006).

**Aucun réglage de paramètre ni mécanisme unique ne rend l'émergence du fourrage
robuste sur les 3 seeds.** Chaque changement rebrasse *quelle* graine tombe dans le
bassin fourrageur, mais l'issue reste **contingente aux conditions initiales**
(effet fondateur). Seed 42 fourrage sous la plupart des réglages ; seed 7 résiste
presque partout (sauf nourriture rare). C'est la signature d'un système
**dominé par la dérive fondatrice**, où la sélection sur le *steering* est trop
faible en absolu pour rendre l'issue déterministe — cohérent avec la contingence
évolutive réelle, mais insatisfaisant si l'on veut une émergence *fiable*.

**Ce qui reste, pour une robustesse réelle — changements structurels (pas des
réglages) :**
1. **Maintien de diversité / niching** (fitness sharing par espèce ; `speciation.py`
   existe déjà comme observateur → le passer en pression) : garde plusieurs bassins
   vivants pour que le bon puisse gagner, au lieu d'un verrouillage précoce.
2. **Population nettement plus grande** (ex. 500–1000) : réduit la dérive
   fondatrice → issue moins stochastique. Config-only mais coûteux en CPU.
3. **Accepter l'émergence stochastique** comme résultat ALife valide : le fourrage
   *émerge* dans une fraction des runs (seed 42 : 99 %) — mesurer un taux de succès
   sur N seeds plutôt que viser 100 % de fiabilité.

**Livrable net de cette session** : diagnostic complet + instrumentation
réutilisable (`tools/steer_probe.py`, `tools/run_and_probe.py`) + `move_cost`
implémenté (défaut 0.0) + 7 configs d'expérience documentées. Rien promu en
`default.yaml` (aucun réglage robuste). La prochaine avancée est structurelle
(niching ou grande population), à décider.

---

## ÉTAPE 7 — Piste 1 : population plus grande (2026-07-06) — ROBUSTESSE OBTENUE

Test du diagnostic « dérive fondatrice » : si l'issue est stochastique parce que N
est petit, une **population plus grande** doit réduire la variance inter-seed
(dérive ∝ 1/N). Isolation propre par **scaling géométrique** (`config/bigpop.yaml`) :
monde ×√2, nourriture ×2, population ×2 (init 200 / max 400), vitesse/capteurs/
rayons mis à l'échelle → **densités et dynamique par agent identiques**, seul N
change (×2). Base L1+L2 (mut 0,15/0,05, drain 0,0015), 15k ticks.

| Config | seed 42 | seed 7 | seed 123 | Lecture |
|--------|---------|--------|----------|---------|
| **L1+L2** (pop ~200) | +0,36 / 99 % | +0,?? / **14 %** | +0,09 / 43 % | variance énorme, quasi-échec seed 7 |
| **bigpop** (pop 400) | +0,34 / 77 % | +0,09 / **58 %** | +0,08 / 39 % | **tous positifs, aucun échec** |

**Résultat : première configuration robuste.** Les 3 seeds fourragent (77/58/39 %),
tous à steering moyen positif. **Seed 7, à 0–14 % sous *toutes* les autres configs,
monte à 58 %.** La variance inter-seed s'effondre (plage 85 pts → 38 pts, plus aucune
population anti-fourrageuse). Le diagnostic « dérive fondatrice » est confirmé :
doubler N suffit à faire basculer le seed récalcitrant dans le bassin fourrageur.

**Compromis observé :** le plafond de seed 42 baisse (99 %→77 %). Attendu : une plus
grande population converge plus lentement (moins de « générations par agent » en
15k ticks). D'où confirmation à 30k ticks (une grande population a-t-elle BESOIN de
plus de temps pour atteindre un plafond élevé *et* robuste ?).

**Statut :** piste 1 = succès sur l'axe robustesse (l'objectif qui résistait à tous
les leviers paramétriques). Reste à confirmer que robustesse + plafond élevé
coexistent (run 30k) avant d'envisager une promotion en défaut.

---

## ÉTAPE 8 — Confirmation 30k : le fourrage n'est pas un attracteur stable

Run bigpop prolongé à 30k ticks (mêmes 3 seeds) pour voir si le plafond remonte
avec plus de temps. Résultat **négatif et éclairant** :

| Seed | bigpop 15k | bigpop 30k | Tendance |
|------|-----------|-----------|----------|
| 42 | +0,34 / 77 % | +0,31 / 74 % | **stable ~75 %** |
| 7 | +0,09 / 58 % | **−0,05 / 25 %** | **redescend** (médiane +0,22→−0,15) |
| 123 | +0,08 / 39 % | +0,06 / 34 % | léger déclin |

**Le fourrage ne se consolide pas — il s'érode.** Doubler le temps n'augmente pas
le fourrage ; il le fait *reculer* (seed 7 : 58 %→25 %). Seule seed 42 tient un
**équilibre stable à ~75 %**. Autrement dit : la grande population réduit la variance
*à un instant donné* (d'où le bon snapshot à 15k) mais **n'ancre pas** le fourrage —
les populations dérivent dedans puis dehors, car la sélection sur le *steering* est
trop faible pour le maintenir.

### Conclusion générale de l'investigation (ÉTAPES 5–8)

Fil rouge unifiant tous les résultats : **le fourrage dirigé est trop faiblement
sélectionné pour être un attracteur évolutif stable dans ce modèle.** Il *peut*
émerger (seed 42 : équilibre stable ~75 % ; seed 7 à 15k : 58 % transitoire), et la
grande population rend l'émergence plus *fréquente* inter-seed, mais rien ne le
*verrouille* : dès que survivre par rencontre aléatoire suffit, l'anti-fourrage
n'est pas puni et la dérive ramène la population vers le neutre.

Deux leviers agissent sur des axes **orthogonaux** :
- **Grande population (piste 1)** → réduit la *dérive* (variance inter-seed, émergence
  plus fiable) mais ne renforce pas la *sélection*.
- **Nourriture rare / coût de déplacement** → renforce la *sélection* (fourrage
  nécessaire) mais seuls, sous petite population, ils *rebrassent* les seeds.

**Hypothèse prédite par le diagnostic, non encore testée :** *combiner* grande
population **ET** nécessité de fourrage (bigpop + nourriture rare, ou bigpop + coût
de déplacement) devrait donner un fourrage **à la fois robuste (faible dérive) et
stable (fortement sélectionné)**. C'est le test le plus prometteur pour la suite.

**Décision défaut :** ne PAS promouvoir bigpop en `config/default.yaml` — robuste en
snapshot mais non stable. Le gain acquis et documenté reste L1+L2 (héritabilité +
sélection, condition nécessaire démontrée) ; la robustesse durable demande la
combinaison ci-dessus, à valider avant toute promotion.

---

## ÉTAPE 9 — Combinaison grande population + nourriture rare : hypothèse falsifiée

Test de l'hypothèse « grande pop (anti-dérive) + nourriture rare (fourrage
nécessaire) → fourrage robuste ET stable ». `config/bigpop_scarce.yaml` : monde ×4
(aire), densité de nourriture 0,37× le défaut (rare), pop max 400 → capacité ~266.
Base L1+L2. 30k ticks.

| Seed | bigpop (nourriture normale, 30k) | bigpop_scarce (30k) | Flip |
|------|----------------------------------|---------------------|------|
| 42 | +0,31 / 74 % | **−0,06 / 2 %** | s'effondre |
| 7 | −0,05 / 25 % | **+0,40 / 96 %** | explose (stable) |
| 123 | +0,06 / 34 % | +0,11 / 49 % | modéré, stable |

*Note : le run de seed 123 avait été interrompu par un `git checkout` externe
accidentel vers `origin/web-integration` (working tree remplacé, src Python retiré) ;
il a été relancé après restauration de `poc2.2` — valeur ci-dessus.*

**Hypothèse FALSIFIÉE.** La combinaison n'est pas robuste. bigpop_scarce donne
{2 %, 96 %, 49 %} : la variance inter-seed (2→96) est en fait **pire** que le régime
abondant (25→74). La composante nourriture-rare **domine** et réimpose son propre
pattern (seed 7 gagne, seed 42 s'effondre — exactement la Remedy B / ÉTAPE 5), et la
grande population ne l'empêche pas. Seed 42 et seed 7 **flippent** dramatiquement
entre les deux régimes (42 : 74 %→2 % ; 7 : 25 %→96 %), seed 123 reste modéré (~40-
49 %) dans les deux. **Chaque seed fourrage dans *un* régime, aucun régime ne
satisfait les trois.**

### Conclusion finale de l'investigation (ÉTAPES 0–9)

Après ~10 configurations et ~30 runs mesurés au niveau population :

1. **L'émergence du fourrage est réelle et démontrée** — dans le bon régime, une
   population passe de anti-fourrageuse (r≈−0,17) à 75–96 % de fourrageurs stables.
2. **Les conditions nécessaires sont identifiées** : héritabilité (mutation basse,
   L1) + sélection (famine/nécessité, L2). Aucune seule ne suffit.
3. **Mais le fourrage stable-ET-robuste-inter-seed n'est PAS atteignable par
   réglage de paramètres dans ce modèle.** Chaque régime (abondant vs rare, petit vs
   grand N) détermine *quel* bassin fondateur gagne ; il n'existe pas de réglage qui
   fasse fourrager tous les seeds. L'issue est **fondamentalement contingente**
   (dépendante des fondateurs), et les régimes qui sauvent un seed en sacrifient un
   autre (frustration).

**Ce qui resterait à tenter (changements structurels, hors réglage) :** coupler la
reproduction directement aux pommes cumulées (fitness = compétence de fourrage
mesurée, pas survie) ; spéciation protectrice / fitness sharing (garder plusieurs
bassins vivants simultanément) ; ou accepter l'émergence contingente comme un
résultat ALife légitime et rapporter un *taux de succès sur N seeds* plutôt qu'une
fiabilité de 100 %.

**Décision défaut : ne rien promouvoir.** Aucun réglage n'est stablement robuste.
Le gain net documenté reste L1+L2 (condition nécessaire) + l'instrumentation
(`tools/steer_probe.py`, `tools/run_and_probe.py`) + `move_cost` (impl. dans
stash@{0}). La suite est structurelle, pas paramétrique.

---

## ÉTAPE 10 — Changement STRUCTUREL : reproduction ∝ pommes cumulées (2026-07-07)

Après l'échec des réglages paramétriques (ÉTAPES 5-9), on implémente le vrai
changement de mécanisme prédit par le diagnostic : **découpler la fécondité de
l'énergie instantanée et la coupler au fourrage cumulé.**

### Implémentation

Param `agent.apples_per_offspring` (défaut 0.0 = legacy énergie ; >0 = structural).
Quand >0, chaque agent banque +1 crédit de reproduction par pomme mangée et dépense
`apples_per_offspring` crédit par enfant → **nombre de descendants ≈ pommes mangées /
K**, linéaire en compétence, sans plafond d'énergie. Au plafond de population, les
mieux-nourris se reproduisent d'abord (priorité par crédit). Deux stratégies dans
`simulation.py` (`_reproduce_by_energy` legacy / `_reproduce_by_foraging`). Le parent
paie toujours `reproduction_cost` énergie par enfant. **143 tests verts (2 nouveaux),
black + pylint 10/10.**

### Résultats (steering moyen population / % fourrageurs, 3 seeds)

| Config | seed 42 | seed 7 | seed 123 | Lecture |
|--------|---------|--------|----------|---------|
| **apple_repro** (K=3, survie libre, 15k) | 37 % | **4 %** | 90 % | viable, sélection forte, mais seed 7 échoue |
| **apple_repro + L2** (drain 0.0015, 15k) | 21 % | **4 %** | 61 % | le drain dur **dégrade** (comme partout) |
| **apple_repro + bigpop** (grande pop N~2×, 15k) | 98 % | **86 %** | 43 % | **1ʳᵉ config sans échec — seed 7 SAUVÉ** |
| **apple_repro + bigpop** (30k, stabilité) | 86 % | **84 %** | 56 % | **TIENT — pas d'érosion** |

**apple_repro seul ne suffit pas** : seed 7 reste à 4 %. Avec survie libre, les
mutants non-fourrageurs des bons parents **survivent** (longévité) et diluent la
population, même s'ils ne se reproduisent pas (le champion seed 7 fourrage pourtant :
record 39, max steer +0,56 — c'est la population qui est diluée).

**apple_repro + bigpop = première configuration robuste ET stable.** Les 3 seeds
fourragent durablement (30k : 86/84/56 %), tous à steering moyen positif ; **seed 7 —
bloqué 4-14 % sous TOUS les autres régimes — atteint 84 % et tient.** Différence
décisive avec le bigpop à repro-énergie (ÉTAPE 8, qui s'érodait 58→25 %) : la
reproduction apple-gated **ancre** le fourrage comme **attracteur stable** (un non-
fourrageur ne se reproduit jamais → le pool génétique reste fourrageur), au lieu d'un
état transitoire.

### Conclusion — la thèse de l'audit v3 est validée

Le blocage n'était ni la représentation (repère de sortie) ni la viabilité, mais
**(a) le couplage sélection↔compétence** trop faible et **(b) la dérive fondatrice**.
Les deux se traitent ENSEMBLE, structurellement :
- **apple-gated reproduction** → sélection directe (fourrager = se reproduire) ;
- **grande population** → faible dérive.

Aucun seul ne suffit (apple_repro seul : seed 7 = 4 % ; bigpop-énergie seul : érode).
Ensemble ils produisent la **première émergence de fourrage robuste (3 seeds) et
stable (30k)** de toute l'investigation. La variance inter-seed subsiste (56-86 %)
mais tous fourragent fortement et durablement.

### Décision défaut

`apples_per_offspring` reste à 0.0 dans `config/default.yaml` (ajout neutre). La config
gagnante `apple_repro_bigpop` (grande pop + apple-gated) est conservée comme référence
d'expérience ; sa promotion en défaut change la taille du monde/population et est à
décider explicitement.
