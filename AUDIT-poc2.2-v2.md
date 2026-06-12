# Audit poc2.2 — v2 : dynamique darwinienne, théorie + code + plan

Cet audit prolonge `AUDIT-poc2.2.md` (qui couvrait les 7 invariants + 4 correctifs).
Il ne répète pas ce qui y figure déjà. Objet : la simulation produit-elle une
**évolution darwinienne authentique** (naissance → survie différentielle →
reproduction avec hérédité mutée → amélioration mesurable → émergence d'espèces) ?

**Verdict en une phrase :** l'architecture logicielle est saine, mais la
simulation **n'évolue pas** — la population s'éteint sans que le fourragement ne
s'améliore, et **aucune métrique** ne permettait de l'observer. Cette v2 (1) ajoute
l'instrumentation qui rend l'évolution mesurable, (2) introduit une vraie pression
de sélection au plafond de population, et (3) recalibre la reproduction sur la base
d'expériences mesurées. **Mais ces mesures, justement, montrent que le blocage de
fond est architectural** (réseau sans mémoire + sorties en repère absolu + sélection
implicite trop faible), pas un simple problème de réglage : la recalibration retarde
l'extinction et approfondit les générations (4→18) sans produire d'adaptation du
comportement. Le travail v2 transforme un échec *invisible et non diagnostiqué* en
un échec *mesuré, expliqué et outillé pour la suite*.

---

## ÉTAPE 0 — La preuve empirique (run headless, seed 42, config par défaut)

Avant toute théorie, le fait têtu. Trajectoire de population observée :

| tick | pop | food dispo / 80 | record_apples | total_repro |
|------|-----|-----------------|---------------|-------------|
| 100  | 138 | 42 | 2 | 38 |
| 300  | 171 | 54 | 3 | 71 |
| 800  | 67  | 71 | 5 | 106 |
| 1500 | 35  | 80 | 5 | 110 |
| 2500 | 34  | 80 | 5 | 128 |
| 3500 | 12  | 80 | 5 | 128 |
| 5100 | 0 (éteinte) | 80 | 5 | 128 |

Trois signaux critiques :

1. **Extinction.** Après un pic à 171 (les agents brûlent leur énergie initiale),
   déclin monotone jusqu'à 0 vers le tick 5 100.
2. **Nourriture non consommée.** `food_available` reste à ~80/80 presque tout le
   run : les pommes ne sont quasiment pas mangées. Ce n'est pas un problème de
   *perception* (à 80 pommes sur 1600×900 et un capteur de 200 px, un agent voit
   en moyenne ~7 pommes dans son rayon) mais de **contrôle** : les réseaux
   aléatoires ne s'orientent pas vers la nourriture qu'ils voient.
3. **Pas d'amélioration.** `record_apples` plafonne à 5 dès le tick 800 et n'évolue
   plus ; `total_reproductions` se fige à 128 vers 2 500 (plus aucune naissance
   ensuite, juste des morts). La sélection n'a pas le temps d'opérer : la
   population meurt avant que la navigation ne s'améliore.

**Conclusion ÉTAPE 0 :** l'objectif fondamental (« amélioration mesurable sur des
dizaines de générations », « voir des espèces apparaître ») n'est aujourd'hui
**pas atteint**. Le système est sous-réplicatif : chaque agent laisse en moyenne
< 1 descendant. C'est le blocage racine ; tout le reste en découle.

---

## ÉTAPE 1 — Audit théorique

### Sélection naturelle

Le modèle n'est **pas** un NEAT générationnel (pas de générations discrètes, pas
de fonction de fitness explicite, pas de tournoi/roulette). C'est un modèle ALife
**continu et asexué** type Polyworld : un agent qui accumule assez d'énergie se
clone (muté), un agent à court d'énergie meurt. La sélection est *implicite* — la
fitness, c'est le taux de reproduction réalisé. C'est plus authentiquement
biologique qu'un NEAT générationnel, et c'est un bon choix.

**Mais la pression est mal calibrée — actuellement trop faible *pour adapter* et
en même temps létale *pour la population*.** Deux régimes opposés se combinent au
pire :
- Le métabolisme est si bon marché (`energy_drain_per_tick = 0.0004`, ~2 500 ticks
  de sursis à jeun) que survivre est presque gratuit → **peu de tri** sur la
  survie → dérive.
- Mais la *reproduction* exige d'accumuler de l'énergie (seuil 1.3 depuis 1.0),
  donc de manger ; or les contrôleurs aléatoires mangent ~1 pomme/vie. Résultat :
  reproduction sous le seuil de remplacement → extinction.

La littérature confirme la tension : « les approches qui évitent la convergence
prématurée en maintenant la diversité le font au prix de l'efficacité » et
« diversifier une population réduit typiquement la pression de sélection »
([overview des méthodes de diversité en GA, CiteSeerX](https://citeseerx.ist.psu.edu/document?repid=rep1&type=pdf&doi=4811bc9bcd24c9a363afe454e6737b48c24f8837)).
Le point clé de Polyworld : *les populations s'adaptent comportementalement dans
les 5 000–10 000 premiers pas de temps* ([Polyworld, Yaeger](https://shinyverse.org/larryy/Polyworld.html))
— **à condition de survivre jusque-là**. Ici l'extinction (~5 100) arrive avant
la fenêtre d'adaptation. Le levier théorique central est donc : *rendre la phase
de bootstrap survivable* (les fourrageurs médiocres doivent à peu près se
remplacer) pour donner à la sélection le temps d'opérer.

**Fonction de fitness — capture-t-elle la bonne chose ?** Le proxy affiché
(`record_apples`) est un *maximum historique d'un seul individu* : il ne fait que
monter et ne dit rien de la compétence *courante* de la population. Une population
qui dégénère garde un `record_apples` figé sur un ancien individu chanceux. Il
fallait une mesure de fitness *courante et normalisée par l'âge* (pommes/tick de
vie) — ajoutée en v2 (`mean_forage_rate`).

**Plateau / stagnation ?** Oui, observé directement (record figé à 5). Cause :
extinction avant adaptation + sélection trop faible sur la survie. Remèdes connus
(novelty search, fitness sharing, ALPS pour la convergence prématurée —
[GECCO/ACM](https://dl.acm.org/doi/10.1145/2739480.2754649)) sont surdimensionnés
ici ; le remède premier est la viabilité de la population.

### Variation & hérédité

- **Mutations de poids :** gaussienne σ=0.2, taux 0.8/connexion. Correct, mais
  **poids non bornés** : marche aléatoire sans limite. Avec sortie linéaire
  toujours écrêtée à `max_speed`, des poids qui explosent → saturation → agent qui
  fonce dans une direction fixe quelles que soient ses entrées (perte de
  réactivité). NEAT borne usuellement les poids. → backlog (clamp configurable).
- **Mutations topologiques :** `add_node`/`add_connection` corrects, DFS anti-cycle
  fiable, innovations historiques cohérentes (via `TRACKER` global). `add_node`
  applique le split canonique NEAT (in→new=1.0, new→out=poids hérité) ; comme
  l'activation cachée est `tanh` (non linéaire), le split n'est pas neutre — c'est
  une mutation réellement exploratoire, acceptable.
- **Couverture de l'espace :** taux structurels nets positifs (add 0.03+0.05 vs
  remove 0.01+0.02) → croissance lente de complexité, cohérent avec la philosophie
  NEAT « complexification » ([Stanley & Miikkulainen 2002, EC](https://nn.cs.utexas.edu/downloads/papers/stanley.ec02.pdf)).
- **Crossover :** absent. En NEAT le crossover s'appuie sur l'alignement par
  numéros d'innovation (déjà présents ici). Mais dans un modèle ALife asexué
  spatialisé, l'absence de crossover est un choix défendable (reproduction =
  clonage). Non bloquant. → backlog si l'on veut accélérer la recombinaison de
  briques utiles.

### Dynamique de population

- **Taille :** `initial 100 / max 200`. Suffisant pour explorer l'espace NEAT au
  début, mais la population réelle s'effondre bien avant le plafond → le plafond
  n'est jamais le facteur limitant ; le facteur limitant est la **viabilité**.
- **Effondrement de diversité :** risque réel (clonage asexué + pas de niching
  explicite). On ne pouvait pas l'*observer* faute de métrique → corrigé en v2
  (`species_count`, `mean_genetic_distance`).
- **Spéciation nécessaire ?** Pour l'objectif « voir des espèces apparaître », il
  faut au minimum *mesurer* les espèces (distance de compatibilité NEAT). La
  *spéciation protectrice* (fitness sharing par espèce, qui empêche une innovation
  topologique d'être immédiatement supplantée — cf.
  [SharpNEAT](https://sharpneat.sourceforge.io/research/speciation-canonical-neat.html),
  [Wikipedia NEAT](https://en.wikipedia.org/wiki/Neuroevolution_of_augmenting_topologies))
  est un levier anti-convergence *à terme*, mais c'est un changement de modèle
  (compétition locale par espèce) à n'introduire qu'après avoir rendu la
  population viable et instrumentée. → backlog priorisé.

### Émergence

- **Inputs/outputs (33→2) :** suffisants pour du fourragement réactif (les rayons
  encodent la direction des pommes ; un réseau peut apprendre « va vers le rayon
  de type pomme le plus proche »). **Insuffisants pour toute stratégie nécessitant
  de la mémoire** (explorer puis revenir, mémoriser un site). C'est un **plafond
  architectural assumé** : l'invariant n°3 interdit la récurrence, et les sorties
  sont en **repère absolu monde** (pas de cap égocentrique) — l'agent recalcule à
  chaque tick un vecteur vitesse absolu, sans état. Polyworld obtient des
  comportements riches précisément parce qu'il a un cap, une vision égocentrique
  et de l'apprentissage hebbien
  ([Polyworld](https://shinyverse.org/larryy/Polyworld.html)). Dans nos
  contraintes, le comportement atteignable plafonne au **fourragement réactif** —
  ce qui reste un objectif d'émergence valable, mais il faut être honnête sur le
  plafond. → backlog : sortie en repère égocentrique / ajout d'un cap (gros
  changement, hors invariants actuels).

### Failles théoriques — classées

🔴 **Critiques (empêchent l'émergence darwinienne)**
1. Population non viable → extinction avant adaptation (bootstrap mortel).
2. Aucune instrumentation de l'évolution (diversité, espèces, générations,
   fitness courante) → impossible de *valider* quoi que ce soit.

🟡 **Importantes (dégradent la qualité évolutive)**
3. Pression de sélection mal répartie : survie quasi gratuite (dérive) mais
   reproduction trop chère (extinction). Au plafond, l'ordre de reproduction était
   positionnel (FIFO), pas fonction de la fitness.
4. Poids non bornés → risque de saturation des contrôleurs.
5. `record_apples` comme seule « fitness » : trompeur (cliquet historique).

🟢 **Souhaitables (métriques / perf / lisibilité)**
6. Pas de crossover, pas de spéciation protectrice (fitness sharing).
7. Plafond architectural : memoryless + repère absolu (émergence limitée au
   réactif).
8. Dispersion des nouveau-nés ±radius (8 px) → clusters denses, épuisement local.

---

## ÉTAPE 2 — Audit code & architecture

L'implémentation est de bonne qualité (typée, testée 120 tests verts au départ,
pylint 10/10, séparation rendu/logique nette). Points relevés :

**genome.py / network.py** — RAS de bloquant. DFS anti-cycle correct, tri
topologique (Kahn + min-heap) calculé une fois à l'init et caché (invariant n°4),
innovations cohérentes. *Note :* `compatibility_distance` (v2) repose sur la
cohérence globale des numéros d'innovation — garantie tant que tous les génomes
passent par le `TRACKER` global (déjà le cas ; un génome rechargé depuis JSON puis
muté ferait exception, déjà noté en v1).

**simulation.py** (le plus critique) —
- Ordre de boucle correct (perception→action→manger ; métabolisme→mort ;
  respawn ; reproduction ; record ; log). Pas de fuite mémoire (`_apples_eaten`
  nettoyé des morts, enfants ajoutés).
- **Bug de sélection (corrigé v2) :** au plafond, la reproduction itérait
  `self.population` dans l'ordre de la liste et s'arrêtait au cap → priorité
  *positionnelle* (les agents en tête de liste), pas *fonctionnelle*. Artefact non
  biologique. Remplacé par un tri par énergie décroissante : sous rareté de places,
  les plus aptes se reproduisent d'abord.
- Performance : `_update_record` fait un `max()` sur ~pop entrées chaque tick
  (O(pop), négligeable). Les métriques de diversité v2 (paires O(pop²)) ne tournent
  qu'aux intervalles de log → coût amorti négligeable devant les raycasts
  (pop×16×80 par tick).

**agent.py** — Fitness (énergie) sans biais. Raycasts : 16 rayons absolus, FOV
360°, first-hit pommes + murs, géométrie correcte (ray-circle / ray-box). *Limite
conceptuelle* (pas un bug) : pas de cap, sorties en repère absolu (cf. ÉTAPE 1
émergence).

**environment.py** — Zone de pénalité gradient correcte (invariant). Spawn pommes
en zone safe (invariant n°6). *Observation :* avec 80 pommes peu consommées, la
pénalité murale n'est presque jamais la cause de mort — la cause de mort dominante
est la vieillesse sans reproduction. La pénalité crée une pression cohérente mais
marginale au régime actuel.

**config/default.yaml** — Cohérent et validé (cross-checks dans `SimConfig`).
Manquaient : paramètres de spéciation/diversité (ajoutés v2). Calibration énergie
↔ reproduction ↔ nourriture à revoir (cf. ÉTAPE 3 / expériences).

### Bugs / incohérences / optimisations — synthèse

- 🟡 **Bug** : priorité de reproduction positionnelle au plafond → **corrigé v2**.
- 🟡 **Incohérence** : `record_apples` présenté comme « Best fitness » (HUD) alors
  qu'il ne mesure pas la population courante → **complété v2** (`mean_forage_rate`).
- 🟢 **Optim/robustesse** : poids non bornés → backlog (clamp).
- 🟢 Dispersion nouveau-nés ±radius (clusters) → backlog.

---

## ÉTAPE 3 — Synthèse & plan d'action

Croisement théorie ↔ code : **le code ne trahit pas la théorie sur la mécanique**
(NEAT-like correct), il la trahit sur les **conditions d'émergence** : pas de
viabilité de population, pas d'observabilité, sélection au plafond non
fonctionnelle. Plan ordonné :

🔴 **BLOQUANT**
- **B1. Instrumentation évolutive** *(fait v2)* (`src/speciation.py` + 6 colonnes
  CSV + `generation`). *Sans elle, aucune amélioration n'est validable.* Source :
  distance de compatibilité NEAT
  ([Stanley & Miikkulainen 2002](https://nn.cs.utexas.edu/downloads/papers/stanley.ec02.pdf),
  [SharpNEAT](https://sharpneat.sourceforge.io/research/speciation-canonical-neat.html)).
- **B2. Viabilité de la population** *(partiel v2 — voir confirmation)*. La
  recalibration retarde l'extinction (5100→9500) et approfondit les générations
  (4→18) mais ne la supprime pas. Source : fenêtre d'adaptation Polyworld (5–10k
  ticks) *à condition de survivre* ([Polyworld](https://shinyverse.org/larryy/Polyworld.html)).
- **B3. Faire évoluer le fourragement** *(non résolu — cause racine confirmée par
  les données)*. C'est LE blocage de l'émergence. Deux leviers, à traiter en
  priorité absolue après v2 :
  - **B3a. Lever le plafond architectural** : passer les sorties en **repère
    égocentrique** (vitesse relative à un cap de l'agent) — voire un cap +
    capteurs égocentriques façon Polyworld. Rend la carte perception→action bien
    plus apprenable. ⚠ Touche l'invariant « sorties = vitesse absolue » → décision
    de design à acter.
  - **B3b. Coupler sélection et performance** : rendre la fécondité fonction de
    l'énergie excédentaire (manger plus → plus de descendants), pour que le
    différentiel de fitness récompense réellement la compétence et non la simple
    survie. Reste dans l'esprit ALife.

🟡 **IMPORTANT**
- **I1. Sélection fonctionnelle au plafond** (priorité par énergie) — *fait v2*.
- **I2. Bornage des poids** (clamp NEAT configurable) — anti-saturation. Backlog.

🟢 **NICE-TO-HAVE — backlog**
- Spéciation protectrice (fitness sharing par espèce) — anti-convergence à terme.
- Crossover NEAT (alignement par innovation, déjà disponible).
- Dispersion des nouveau-nés (rayon de naissance configurable).

---

## ÉTAPE 4 — Implémentation (ce qui a été changé, et pourquoi)

### Livré dans ce commit-group (B1 + I1)

1. **`src/speciation.py`** — distance de compatibilité NEAT (équation 2,
   non normalisée, comme l'implémentation canonique : `δ = c₁·E + c₂·D + c₃·W̄`),
   comptage d'espèces (clustering glouton sur seuil), distance génétique moyenne
   par paires. **Observateurs en lecture seule** : ils ne rétroagissent jamais sur
   la sélection (le modèle reste ALife continu asexué).
2. **`config` : section `speciation`** — coefficients canoniques (c₁=c₂=1.0,
   c₃=0.4, seuil 3.0). Invariant n°1 respecté (aucun nombre magique en dur).
3. **`Agent.generation`** — profondeur de lignée (fondateur 0, enfant = parent+1).
4. **`Simulation` : 6 colonnes CSV** ajoutées *en fin* de ligne (indices existants
   inchangés) : `max_generation`, `mean_generation`, `species_count`,
   `mean_genetic_distance`, `mean_forage_rate`, `max_forage_rate`.
   `forage_rate = pommes / max(âge,1)` = proxy de fitness *courante*, normalisé par
   l'âge (une hausse de `mean_forage_rate` au fil du temps = preuve directe que la
   sélection améliore les contrôleurs).
5. **`Simulation` : reproduction par priorité d'énergie au plafond** — remplace le
   FIFO positionnel. Tri stable (déterminisme préservé sur les égalités).
6. **+14 tests** (distance/espèces, suivi de génération, priorité au plafond,
   colonnes CSV évolutives). **134 tests verts, pylint 10.00/10, black propre.**

### Recalibration de viabilité (B2)

**Protocole.** Trois runs headless, seed 42, 4 000 ticks, mêmes métriques v2, dans
des dossiers de log distincts. Diagnostic clé de l'ÉTAPE 0 : les pommes sont vues
mais pas mangées → goulot de **contrôle**, pas de perception ; et la population
meurt avant que la sélection n'améliore la navigation. Le levier testé : rendre la
reproduction moins chère (plus de descendants par pomme → renouvellement plus
rapide → plus de générations / d'événements de sélection, et fourrageurs médiocres
plus proches du remplacement). E2 ajoute aussi de la nourriture pour vérifier
qu'elle n'est *pas* le levier.

| Variante | `reproduction_threshold` | `reproduction_cost` | nourriture |
|----------|--------------------------|---------------------|------------|
| **E0** (défaut v1) | 1.3 | 0.6 | 80, respawn 150 |
| **E1** (adoptée)   | **1.1** | **0.35** | 80, respawn 150 |
| **E2** (probe)     | 1.1 | 0.35 | 120, respawn 100 |

**Résultats** (E0/E1 à 4 000 ticks ; E2 lu vers tick 3 600) :

| Métrique | E0 (défaut v1) | E1 (adoptée) | E2 (+ nourriture) |
|----------|----------------|--------------|-------------------|
| population | **1** (extinction imminente) | **57** (oscille 30–90, viable) | **200→143** (plafonnée) |
| total_reproductions | 98 (figé dès ~2500) | 360 | **861** |
| max_generation | **4 → 0** (lignées profondes meurent) | **18** (moy. 9.4) | 17 (moy. 7.4) |
| record_apples | 4 | 6 | **8** |
| species_count | **1** (jamais d'espèce) | **2** | **1** (converge) |
| mean_genetic_distance | ~1.0 puis 0 | **1.4** (diversité préservée) | **0.3–0.5** (effondrée) |
| mean_forage_rate | **décroît** 0.0015→0.0003 | bruité, sursauts ~0.003 | ~0.0017 |

**Lecture.** E0 confirme l'échec noir sur blanc : `max_generation` plafonne à 4
puis retombe à 0, `species_count` reste à 1, `mean_forage_rate` **diminue** (la
population *régresse*). E1 inverse la dynamique : pas d'extinction,
`max_generation` 18 (vers tick 3600 un sursaut de reproduction accompagne un
creux→rebond de population — signature d'un événement adaptatif), 2ᵉ espèce qui
apparaît, diversité génétique préservée.

**E2 illustre la théorie de façon spectaculaire** : plus de nourriture → capacité
de charge plus grande → la population sature le plafond (200) → **une seule lignée
remplit les places → 1 espèce, distance génétique effondrée (0.3–0.5)** =
convergence prématurée. E2 a la plus grosse population et le meilleur
`record_apples` (8), mais c'est le **pire** pour l'objectif « voir des espèces » :
l'abondance affaiblit la sélection et homogénéise la population (cf.
[overview diversité/convergence prématurée](https://citeseerx.ist.psu.edu/document?repid=rep1&type=pdf&doi=4811bc9bcd24c9a363afe454e6737b48c24f8837)).
Donc **garder la nourriture à 80** (E1, pas E2) : la rareté relative maintient la
pression de sélection ET la diversité. La nourriture n'était pas le goulot de
viabilité — la conversion pomme→descendant l'était.

**Décision.** La calibration E1 (`reproduction_threshold 1.1`,
`reproduction_cost 0.35`) est adoptée comme nouveau défaut : elle débloque la
condition nécessaire (viabilité + profondeur générationnelle + apparition
d'espèces). C'est une stratégie *r* assumée durant la colonisation ; la sélection
reste préservée car (a) il faut toujours manger pour se reproduire et (b) au
plafond, la priorité-énergie (I1) fait que les plus aptes occupent les places.

**Réserve honnête.** À 4 000 ticks, `mean_forage_rate` ne montre pas encore de
hausse *directionnelle* nette (bruit + oscillations boom-bust). E1 prouve la
viabilité et la profondeur générationnelle ; il ne prouve pas *encore* une
amélioration monotone du fourragement — soit la fenêtre est trop courte, soit le
plafond architectural (memoryless + repère absolu) bride le gain. Un run long
(12 000 ticks) sur la config adoptée est lancé pour trancher ; voir la section
suivante.

### Run de confirmation (12 000 ticks, config adoptée, seed 42)

Résultat décisif — et qui impose l'honnêteté : **E1 retarde l'extinction mais ne
la supprime pas.** Trajectoire : pic ~96, oscillations, puis spirale de mort après
~tick 5000 → population à 1 dès ~tick 8000, run terminé éteint au tick 9500 (avant
les 12 000 visés).

- Côté positif : `max_generation` atteint **18** (vs 4 pour E0), `species_count`
  touche 2, `mean_genetic_distance` monte à ~1.4. Pendant ~5000 ticks on observe
  donc *bien plus* de dynamique darwinienne qu'en E0 (extinction 5100 → 9500).
- Côté négatif, et c'est le point capital : **`mean_forage_rate` ne monte
  jamais** — moyenne des 20 premières lignes de log 0.00142 → 20 dernières 0.00060
  (en *baisse*). Le fourragement ne s'améliore pas ; `record_apples` (6) ne
  progresse qu'au gré de la loterie reproductive, pas par hausse de la compétence
  *moyenne*.

**Conclusion sans détour.** La recalibration améliore la *démographie* et la
*profondeur générationnelle*, mais ne produit pas d'*adaptation comportementale*.
Le goulot n'est pas (seulement) la calibration énergétique : **les contrôleurs
n'évoluent pas vers le fourragement.** Causes probables, par ordre d'impact :

1. **Plafond architectural.** Réseau sans mémoire + sorties en *repère absolu
   monde* : l'agent doit réaliser une carte 32→vitesse-absolue, recalculée à
   chaque tick sans état. Le gradient de fitness vers « foncer sur la pomme vue »
   est étroit, et la sélection implicite (survie quasi gratuite) est trop faible
   pour le remonter avant dérive/mort.
2. **Sélection découplée de la performance.** Tout agent qui mange ~1 pomme se
   reproduit ; en manger 5 ne donne pas 5× plus de descendants viables sur la
   durée → différentiel de fitness trop plat pour récompenser la compétence.

→ Le vrai levier d'émergence est dans le **backlog 🟢/🟡** (sortie
égocentrique/cap pour lever le plafond ; couplage sélection↔performance plus fort,
ex. fécondité proportionnelle à l'énergie excédentaire ; éventuellement fitness
sharing par espèce), **pas dans un énième réglage de seuil**.

**Sur le choix de calibration adopté.** E1 (nourriture 80) est conservée comme
défaut parce qu'elle domine strictement E0 sur seed 42 (générations 4→18, 1→2
espèces, extinction 5100→9500) *et* préserve la diversité, là où E2 (nourriture
120) achète la stabilité démographique au prix d'une convergence à 1 espèce. Mais
c'est une amélioration **partielle** : un seul seed, extinction toujours présente,
fourragement non amélioré. Pour une viabilité *durable* sans sacrifier la
diversité, il faut traiter la cause architecturale, pas la calibration. Stopgap si
l'on veut juste une population persistante à observer : nourriture intermédiaire
(~90–100) — au prix d'un peu de diversité.

---

## Métriques attendues pour valider l'amélioration

Une fois la population viable, lire le CSV doit montrer, sur un long run :
1. **Population** qui se stabilise (≈ plafond) au lieu de s'éteindre.
2. **`mean_forage_rate`** qui **monte** dans le temps (adaptation réelle, pas
   dérive) — c'est LE signal d'« amélioration mesurable ».
3. **`max_generation`** qui croît de façon soutenue (des dizaines de générations).
4. **`species_count` > 1** maintenu et/ou **`mean_genetic_distance`** non effondrée
   (diversité préservée → « espèces qui apparaissent »).
5. **`avg_network_size`** en lente croissance (complexification NEAT).

Signaux d'alerte : `mean_genetic_distance → 0` (convergence prématurée, une seule
lignée) ; `mean_forage_rate` plat (pas d'adaptation : sélection trop faible ou
plafond architectural atteint).

**Ce qu'on observe réellement aujourd'hui (post-v2, seed 42)** : critère 1 partiel
(population viable ~5000 ticks puis spirale de mort) ; **critère 2 ÉCHOUE**
(`mean_forage_rate` décroît) ; critère 3 partiel (`max_generation` 18 puis
retombe) ; critère 4 partiel (jusqu'à 2 espèces, diversité ~1.4, mais pas
maintenu) ; critère 5 quasi nul (`avg_network_size` ~101, presque pas de
complexification). Autrement dit : l'instrumentation marche et *prouve* que
l'adaptation comportementale n'a pas lieu → priorité au backlog architectural.

---

## Backlog priorisé (post-v2)

Priorité décidée par les données : le levier d'émergence est en tête, pas les
réglages cosmétiques.

1. 🔴 **Sortie égocentrique + cap d'agent** (B3a) — lève le plafond d'émergence
   (nécessite de revisiter l'invariant « sorties = vitesse absolue »).
2. 🔴 **Fécondité ∝ énergie excédentaire** (B3b) — couple sélection et performance.
3. 🟡 Clamp de poids configurable (`genome.weight_max`) — anti-saturation.
4. 🟢 Spéciation protectrice (fitness sharing par espèce) — anti-convergence.
5. 🟢 Crossover NEAT par alignement d'innovations.
6. 🟢 Dispersion des nouveau-nés (rayon de naissance configurable).
7. 🟢 `TRACKER` non global (permettre 2 simulations simultanées dans un process).
8. 🟢 Durabilité CSV : le fichier reste ouvert et n'est vidé qu'à la fermeture
   (un kill brutal perd les lignes bufferisées ; le `finally`/Ctrl-C de `main.py`
   les sauve bien). Un `flush()` périodique dans `_log_row` rendrait les longs
   runs robustes aux interruptions.

## Sources
- Stanley & Miikkulainen 2002, *Evolving Neural Networks through Augmenting
  Topologies*, Evolutionary Computation —
  https://nn.cs.utexas.edu/downloads/papers/stanley.ec02.pdf
- Speciation in Canonical NEAT (formule de distance de compatibilité) —
  https://sharpneat.sourceforge.io/research/speciation-canonical-neat.html
- NEAT (spéciation, protection des innovations) — Wikipedia —
  https://en.wikipedia.org/wiki/Neuroevolution_of_augmenting_topologies
- Polyworld (émergence du fourragement / espèces, fenêtre 5–10k pas) —
  https://shinyverse.org/larryy/Polyworld.html
- Méthodes de maintien de diversité / convergence prématurée (overview) —
  https://citeseerx.ist.psu.edu/document?repid=rep1&type=pdf&doi=4811bc9bcd24c9a363afe454e6737b48c24f8837
- Structure Fitness Sharing (diversité structurelle, GECCO 2015) —
  https://dl.acm.org/doi/10.1145/2739480.2754649
