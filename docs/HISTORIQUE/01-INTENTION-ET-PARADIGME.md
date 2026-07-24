# 01 — Intention et paradigme : le POURQUOI du projet

> Ce chapitre pose le cadre scientifique : la question de recherche, le paradigme
> choisi, les contraintes assumées, et les invariants de conception lus comme des
> choix scientifiques (pas comme des règles arbitraires). Tout le reste du corpus
> découle de ce cadre.

---

## 1. La question de recherche

Le projet part d'une ambition simple à énoncer, difficile à réaliser :

> **Peut-on faire émerger un comportement de fourrage *dirigé et adaptatif*
> — pas seulement *viable* — par évolution seule, dans un écosystème artificiel
> minimal ?**

La distinction *viable* vs *adaptatif* est le pivot de tout le projet :
- **Viable** = la population survit, se reproduit, ne s'éteint pas. C'est
  atteint très tôt (dès poc2.1).
- **Adaptatif** = les agents *apprennent effectivement* à se diriger vers la
  nourriture, et cette compétence est *héritée* et *sélectionnée* génération
  après génération, de façon **robuste** (elle tient sur plusieurs graines
  aléatoires) et **stable** (elle tient dans la durée, 30 000 ticks).

Le constat qui lance l'investigation (poc2.2) : **la population survit très bien,
mais n'apprend rien à fourrager.** Après 24 000 ticks, le « champion » est un
perceptron aux poids quasi aléatoires qui s'oriente *à l'opposé* des pommes
(corrélation r = −0,17) — et 143 nouveau-nés aléatoires sur 200 font mieux que
lui. La survie est quasi gratuite, donc le fourrage n'est presque pas sélectionné.

**Fil rouge unique de tout le projet** : *le fourrage dirigé est trop faiblement
sélectionné pour être un attracteur stable.* On ne le corrige jamais par un
simple réglage de paramètre — seulement en changeant le **mécanisme** (renforcer
le couplage sélection↔compétence, et réduire la dérive fondatrice).

---

## 2. Le paradigme : ALife + NEAT écrit à la main

Le projet relève de la **vie artificielle** (ALife) et de la
**neuroévolution** :

- **Écosystème** : un monde 2D continu, des agents mobiles, des pommes qui
  spawnent dans une zone sûre, une zone de pénalité murale à gradient. Les agents
  ont une énergie qui décroît par tick, se rechargent en mangeant, se reproduisent
  quand ils en ont les moyens, meurent de famine ou de vieillesse.
- **Cerveau = réseau de neurones** feedforward, dont la **topologie et les poids
  évoluent** par mutation (façon NEAT — NeuroEvolution of Augmenting Topologies,
  Stanley & Miikkulainen 2002), écrit **entièrement à la main** en Python.
- **Pas d'apprentissage par gradient** : aucune backprop, aucune fonction de
  perte. Les poids ne sont jamais entraînés — ils sont *évolués* par sélection
  différentielle sur la reproduction. C'est la différence de fond avec le RL
  classique.

Ce choix paradigmatique a une conséquence structurante, qui reviendra sans cesse :
comme il n'y a **pas d'épisode d'entraînement**, tout le signal d'apprentissage
passe par **qui se reproduit**. Si la reproduction ne discrimine pas les bons
fourrageurs, il n'y a littéralement aucun canal par lequel la compétence peut
s'installer. C'est ce qui rend le « couplage sélection↔compétence » central.

---

## 3. La contrainte « aucun framework ML » — son histoire

C'est une contrainte de conception **assumée et datée**, pas un dogme :

- **À l'origine** : contrainte forte « aucun framework ML ». Le NEAT est écrit à
  la main (génome, mutations, réseau, forward pass), pour que la mécanique
  évolutive soit **entièrement comprise et maîtrisée**, pas déléguée à une boîte
  noire. C'est un projet de compréhension, pas de performance brute.
- **Levée le 2026-07-16** (pour la branche poc3) : NumPy était déjà autorisé
  (et utilisé dès poc2.3 pour vectoriser le raycast). La levée élargit à tous les
  moyens de calcul utiles (CuPy, JAX, Numba, scipy…) **si utile**.
- **Reconduite explicitement par Robin le 2026-07-20** au retour sur poc2.6 : la
  question est donc tranchée, elle ne se repose plus.

**Restent interdits en permanence** : `neat-python` et `gym`. La raison n'est
**pas** une question de performance — c'est scientifique : ce sont des
**encodages / environnements RL tout faits**, qui court-circuiteraient
précisément ce que le projet cherche à étudier (la mécanique évolutive et la
dynamique de la tâche, construites à la main).

> Note de clôture (poc2.6) : même avec la contrainte levée, un RL classique
> (Q-learning / policy gradient) reste hors cadre — il suppose une boucle
> d'entraînement séparée, en tension avec le principe « réseau feedforward +
> évolution seule ». Et le résultat de poc2.6 suggère qu'il buterait de toute
> façon sur le même mur : ~3 événements informatifs par vie d'agent (voir `09`).

---

## 4. Les invariants de conception, lus comme des choix scientifiques

Le projet s'impose 7 invariants (dans `CLAUDE.md`). Ils ne sont pas cosmétiques :
chacun protège la validité scientifique des expériences.

1. **Zéro valeur hardcodée** — tout paramètre vient de la config YAML typée
   (`SimConfig`). *Pourquoi* : une expérience de falsification n'a de sens que si
   on peut **isoler une seule variable** ; un nombre magique caché dans le code
   est une variable non contrôlée. C'est ce qui rend la méthode « une variable à
   la fois » possible.
2. **Énergie en pommes-équivalent PAR TICK**, jamais par frame. *Pourquoi* :
   découpler la dynamique de simulation de la cadence de rendu — sinon le
   comportement dépendrait de la vitesse de la machine.
3. **Topologie NEAT variable, mais strictement feedforward** — les mutations
   structurelles existent (`add_node`, `add_connection`, `remove_*`), et le
   feedforward est garanti par une **vérification DFS anti-cycle** dans
   `add_connection`. *Pourquoi* : jamais de connexion récurrente → le réseau est
   une fonction pure de ses entrées, donc le comportement est **déterministe et
   reproductible** (crucial pour la traçabilité, voir `11`).
4. **Réseau construit une fois, mis en cache** (tri topologique caché à l'init de
   l'agent, jamais recalculé pendant sa vie). *Pourquoi* : perf + garantie que le
   « cerveau » d'un agent est figé pendant sa vie (ce qui rend le levier de
   plasticité de poc2.6 d'autant plus notable — c'est le premier à violer cette
   fixité).
5. **Sorties égocentriques** : `heading += output[1] × max_turn_rate` ;
   `speed = output[0] × max_speed` (signée, `tanh ∈ (−1,1)`) ;
   `vx, vy = speed × cos/sin(heading)`. *Pourquoi* : l'agent commande *son propre
   virage et sa propre vitesse*, pas des coordonnées absolues — un repère
   biologiquement plausible et invariant par translation/rotation du monde.
6. **Pommes uniquement dans la zone safe** (hors zone de pénalité). *Pourquoi* :
   ne pas créer d'incitation contradictoire (aller chercher une pomme au prix de
   la pénalité murale brouillerait le signal de fourrage).
7. **Renderer séparé de la logique** — `simulation.py` ne touche jamais Pygame.
   *Pourquoi* : la simulation doit tourner **headless** (sans affichage) pour les
   campagnes en masse ; le rendu est un observateur, pas un acteur.

---

## 5. Ce que « inputs / outputs » veut dire concrètement

**Entrées (layout configurable, `num_inputs` dérivé — jamais hardcodé).** Le
défaut est **49 inputs** (`3 × num_rays + 1`, avec `num_rays = 16`) :
- `[0-15]` distance au plus proche objet par raycast, normalisée `[0→1]`
- `[16-31]` drapeau « pomme » (0/1) par raycast
- `[32-47]` drapeau « mur » (0/1) par raycast
- `[48]` énergie normalisée `[0→1]`

Un layout **riche à 67 inputs** existe (distance pomme/mur séparée +
proprioception + `apples_in_view`) mais il **casse la robustesse** — voir `05`.
Le choix du 49 par défaut est une **décision empirique**, pas esthétique.

**Sorties (2)** → post-traitement égocentrique (invariant n°5) :
- `output[0] × max_speed` = vitesse avant/arrière (signée)
- `output[1] × max_turn_rate` = delta de cap (rad/tick)

---

## 6. Pourquoi cette rigueur méthodologique compte

Le projet ne se juge pas à un « grand résultat » unique, mais à la **qualité de
son raisonnement de falsification** : 13 leviers écartés, chacun avec un
diagnostic mécanistique (pas juste un mauvais score), et un fil rouge qui se
renforce à chaque échec. Le cadre posé ici — une variable à la fois, tout piloté
par config, déterminisme strict — est précisément ce qui rend ces falsifications
**crédibles et rejouables**. La méta-histoire de cette rigueur est le chapitre
`11`.
