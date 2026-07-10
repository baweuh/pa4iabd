# Compte rendu de soutenance — ALife Neuroevolution

> Document de travail pour générer la présentation (10 min + démo 1-2 min).
> Synthèse transverse de tout le projet : intentions, directions prises,
> expériences, résultats, répartition du temps, difficultés.

---

## 0. Le projet en une phrase

Un **écosystème artificiel** où des agents apprennent à survivre **par sélection
naturelle**, sans aucun framework de machine learning. Chaque agent est piloté
par un petit **réseau de neurones** dont la structure et les poids **évoluent de
génération en génération** (approche NEAT, réécrite entièrement à la main en
Python). On ne dit jamais à un agent quoi faire : on lui donne des yeux
(raycasts), un cerveau (réseau) et une contrainte vitale (l'énergie). Ceux qui
trouvent les pommes et évitent les murs se reproduisent ; les autres meurent.

**La thèse défendue** : faire *émerger* un comportement intelligent — pas
l'entraîner.

---

## 1. Les intentions (pourquoi ce projet)

Trois intentions, par ordre d'importance :

1. **Comprendre la neuroévolution de l'intérieur.** Interdiction volontaire de
   `neat-python`, PyTorch, TensorFlow, Gym. Tout est codé à la main — génome, tri
   topologique, forward pass, mutations, détection de cycle — pour vraiment saisir
   la mécanique au lieu d'appeler une bibliothèque.
2. **Un terrain d'observation de l'émergence.** Voir en direct des comportements
   *non programmés* (chasse, évitement) apparaître sous la seule pression de
   sélection.
3. **Un projet d'ingénierie propre.** Architecture stricte, invariants
   documentés et vérifiés, tests à chaque module, séparation nette logique / rendu.

---

## 2. La boucle de vie d'un agent (le cœur du modèle)

- **Percevoir** — 16 raycasts à 360° renvoient distance + type (rien / pomme /
  mur) → entrées du réseau.
- **Décider** — le réseau feedforward produit 2 sorties.
- **Agir** — sorties *égocentriques* : `heading += sortie₂ × max_turn`,
  `vitesse = sortie₁ × max_speed`. L'agent tourne et avance, consomme de l'énergie
  à chaque tick.
- **Manger** — une pomme rend de l'énergie ; la zone près des murs en draine
  (gradient de pénalité, pas binaire).
- **Se reproduire** — au-dessus d'un seuil, l'agent clone son génome avec
  mutations.
- **Mourir** — de faim (énergie 0) ou de vieillesse (âge max).

---

## Glossaire — le vocabulaire à connaître pour suivre

*(À placer sur une slide « repères » avant d'entrer dans les résultats, ou à
distiller à l'oral au fil de la présentation.)*

- **Neuroévolution** — faire évoluer des *réseaux de neurones* par sélection
  naturelle (mutation + reproduction des meilleurs), au lieu de les *entraîner*
  par descente de gradient. Pas de « bonne réponse » donnée à l'agent : seule la
  survie tranche.
- **NEAT** *(NeuroEvolution of Augmenting Topologies)* — la méthode de référence
  qu'on a réécrite à la main : le réseau **grossit** au fil des générations
  (ajout de neurones et de connexions par mutation), il ne part pas d'une taille
  figée.
- **Génome** — la « recette » d'un agent : la liste de ses neurones et connexions.
  C'est lui qui mute et se transmet à la reproduction.
- **Feedforward** — réseau sans boucle : l'information va des entrées vers les
  sorties, jamais en arrière. Garanti à chaque mutation (invariant du projet).
- **Raycast** — un « rayon de vision » lancé depuis l'agent ; il renvoie la
  distance et la nature (rien / pomme / mur) du premier objet touché. 16 rayons à
  360° = les yeux de l'agent.
- **Tick** — une étape de simulation (l'unité de temps du monde). Un run typique
  fait 15 000 à 30 000 ticks. Tout se compte *par tick*, jamais par image écran.
- **Seed** — la graine du générateur aléatoire. Même seed = simulation
  reproductible à l'identique. On teste **toujours 3 seeds** (42, 7, 123) pour
  distinguer un vrai progrès d'un coup de chance sur une seule partie.

### Les deux mots-clés des résultats

- **Fourrageur** *(forager)* — un agent qui **cherche activement la nourriture** :
  quand une pomme apparaît à sa gauche, il tourne à gauche. C'est ça, le
  comportement « intelligent » qu'on veut voir émerger. Son contraire, un agent
  qui ignore les pommes ou s'en éloigne, n'est **pas** un fourrageur même s'il en
  avale quelques-unes par hasard en errant.
- **% de fourrageurs** — **la métrique centrale du projet.** C'est la *proportion
  de la population vivante qui fourrage vraiment*. On mesure ça avec une **sonde
  comportementale** (`steer_probe`) : on présente une pomme isolée à chaque agent
  et on mesure s'il tourne vers elle (corrélation de Pearson *r* entre « pomme à
  gauche » et « tourne à gauche »). Un agent compte comme fourrageur si *r > 0,1*.
  - **86 %** veut donc dire : *86 % des agents vivants s'orientent réellement vers
    la nourriture.* C'est une mesure de **compétence collective**, pas un score
    d'un seul champion.
  - **Pourquoi cette métrique et pas « le nombre de pommes mangées » ?** Parce que
    le nombre de pommes est **trompeur** : un agent qui vit longtemps en tournant
    en rond percute des pommes par accident et accumule un gros score sans aucune
    stratégie. Compter les pommes mesure surtout la *longévité et la chance*, pas
    l'*intelligence*. Le % de fourrageurs, lui, teste directement la stratégie.
    Construire cette sonde a été le déclic de tout le projet (voir §4.1).

---

## 3. Les fondations — le socle technique (Phases 1-8, juin)

Livré **phase par phase, chaque brique testée isolément** avant de passer à la
suivante. ~3000 lignes de code source, ~2000 lignes de tests, 148 tests.

| Phase | Livré | Difficulté technique notable |
|-------|-------|------------------------------|
| 1 | Config typée (dataclasses) + YAML — **zéro nombre magique** | Invariant central : tout paramètre vient du YAML |
| 2 | Génome NEAT : nœuds/connexions, 5 mutations, **DFS anti-cycle**, compteur d'innovation | Garantir un graphe **toujours acyclique** après mutation |
| 3 | Réseau feedforward : **tri topologique caché à l'init**, forward pass | Calculer l'ordre d'évaluation une seule fois, jamais recalculé |
| 4-5 | Environnement (pommes en zone safe, gradient de pénalité) + Agent (raycasts, énergie, cycle de vie) | Raycasting maison, comptabilité énergétique par tick |
| 6 | Boucle de simulation fixed-timestep, gestion population, extinction propre, CSV | Découpler la logique du rendu |
| 7-8 | Rendu Pygame **totalement séparé** de la logique + CLI (visuel / headless) | `simulation.py` ne touche jamais Pygame |

**Décisions structurantes** : réseau *strictement* feedforward (jamais de
récurrence), sorties égocentriques, tout piloté par YAML, rendu séparable pour
tourner sans interface (mode headless → CSV).

---

## 4. Le fil rouge de recherche : « pourquoi ça n'évolue pas ? »

C'est **le cœur du projet et ce qui a demandé le plus d'ingéniosité.** Une fois
le simulateur fonctionnel, un constat : la population **survit** mais
n'**apprend** rien à fourrager. On entre en mode investigation scientifique.

### 4.1. Le diagnostic (poc2.2) — enquête forensique

Le premier réflexe aurait été de croire le meilleur agent « intelligent » parce
qu'il avait mangé le plus de pommes. On a refusé de s'en contenter et **construit
un instrument de mesure** (`steer_probe`) : on isole l'agent, on fait apparaître
une seule pomme à sa gauche (puis à sa droite) et on regarde s'il tourne *vers*
elle. La corrélation entre « pomme à gauche » et « tourne à gauche » donne un
score : +1 = fourrageur parfait, 0 = indifférent, négatif = fuit la nourriture.
Verdict brutal :

> Après 24 000 ticks, le « champion » (record 27 pommes) est un **cerveau nu aux
> connexions quasi aléatoires** qui s'oriente **à l'opposé** des pommes
> (corrélation −0,17). Sur 200 nouveau-nés tirés au hasard, **~72 % font mieux que
> lui.** Ses 27 pommes venaient de la *longévité* : en vivant 5 000 ticks dans un
> monde plein de pommes, un marcheur aléatoire en percute une trentaine. **Rien
> n'avait été appris.**

**La grande leçon méthodologique** : la métrique évidente (nombre de pommes
mangées) était **trompeuse** — elle mesurait surtout la longévité et la chance,
pas la compétence. Il a fallu *inventer le bon instrument de mesure* — le % de
fourrageurs — avant de pouvoir juger quoi que ce soit. **C'est la partie la plus
difficile et la plus formatrice du projet.**

**Quatre causes racines identifiées** :
1. La sélection sur le fourrage est **minuscule** (survivre est quasi gratuit).
2. La charge de mutation **détruit l'héritabilité** (80 % des poids re-randomisés
   par génération).
3. La complexification NEAT **ne s'enclenche jamais** (fondateur déjà tout-connecté).
4. La bonne métrique manquait.

### 4.2. La campagne de réglages — l'échec instructif

~10 configurations, ~30 runs, sur **3 seeds** (pour distinguer un vrai effet du
hasard du seed). Leviers testés : taux de mutation, drain d'énergie, énergie max,
densité de nourriture, coût de déplacement.

> **Aucun réglage de paramètre ne rend le fourrage robuste sur les 3 seeds.**
> Chaque régime ne fait que **rebrasser quel seed gagne** (effet fondateur).

Conclusion forte : le blocage n'est **pas un problème de réglage**, c'est un
problème de **mécanisme**.

### 4.3. La percée — changer le mécanisme, pas le paramètre

Nouveau mécanisme : la **fécondité proportionnelle aux pommes cumulées** (et non à
l'énergie du moment). Concrètement, chaque pomme mangée donne un crédit de
reproduction ; un agent qui ne fourrage pas n'a aucun crédit et **ne se reproduit
jamais**. Le fourrage devient donc directement récompensé — c'est un
**attracteur** de l'évolution. Couplé à une **grande population** (qui limite la
dérive due au hasard) :

| Config (30 000 ticks) | seed 42 | seed 7 | seed 123 |
|------------------------|---------|--------|----------|
| **% de fourrageurs** `apple_repro_bigpop` | 86 % | **84 %** | 56 % |

**Première émergence de fourrage robuste (les 3 seeds) ET stable (tenue à 30 000
ticks).** Lecture : sur chaque seed, la majorité des agents vivants s'orientent
désormais vraiment vers la nourriture. Le seed 7 — bloqué à 4-14 % sous *tous* les
autres réglages — atteint 84 %. **Le comportement intelligent a émergé sans jamais
être programmé.**

> **Et le « record en pommes » alors ?** Il monte lui aussi (de ~27 à ~50 pommes
> pour le meilleur individu selon les runs), mais on ne s'appuie **pas** sur ce
> chiffre : il reste plombé par la longévité (§4.1). La preuve que quelque chose a
> été *appris*, c'est le % de fourrageurs — pas le record.

---

## 5. poc2.3 — pousser plus loin : six volets d'expériences

Chaque volet = **une hypothèse falsifiable, une seule variable modifiée** par
rapport au contrôle. Démarche scientifique stricte. *(Les résultats se lisent
toujours en % de fourrageurs sur les 3 seeds — voir glossaire.)*

| Volet | Hypothèse | Résultat |
|-------|-----------|----------|
| 1 — Perception riche | +18 entrées (distances pomme/mur séparées, proprioception, pommes en vue) + **visualisation live du réseau** | 🟡 Livré et utile pour l'observabilité, mais… (voir volet 5) |
| 2 — Plus de mutation | Augmenter `add_node_rate` fera émerger des neurones cachés | ❌ Falsifié : 0 neurone caché, ne fait qu'accélérer la dérive |
| 3 — Crossover NEAT | Recombiner deux parents intra-espèce débloque le fourrage | 🟡 Gros effet mais **seed-dépendant** (2/3 seeds améliorés, 1 régressé) |
| 4 — Crossover + population | Combiner les deux meilleurs leviers referait le 3/3 | ❌ Falsifié : la combinaison **sous-performe chaque levier seul** |
| 5 — Ablation du capteur | Le capteur riche (67 entrées) casse-t-il la robustesse ? | ✅ **Décisif** : oui, retour au capteur simple (49) |
| 6 — Génome sparse | Démarrer avec peu de connexions réduira l'instabilité | ❌ Falsifié, plus lourdement que tout le reste |

**L'enseignement transverse (le résultat scientifique du projet)** :

> Dans ce régime, **tout mécanisme qui réduit la richesse effective au démarrage**
> (crossover qui *moyenne* les comportements, connectivité réduite qui *prive*
> d'information, dimensionnalité d'entrée trop grande) **nuit** — même quand la
> théorie est solide. **Seuls les leviers *additifs* ont marché** : plus de
> population, plus de sélection directe. C'est contre-intuitif et c'est le
> principal apport.

Détail marquant du volet 5 : le capteur « riche » (67 entrées) faisait
s'effondrer un seed de **43 % → 1 %**. Aucun canal isolé n'était coupable — c'est
la **dimensionnalité elle-même** (génome fully-connected plus large = plus de
surface de mutation à régler = plus d'instabilité). On est *revenu en arrière* sur
une amélioration apparente, preuve à l'appui.

---

## 6. Le volet web — la démo (branche `web-integration`)

Portage **complet du moteur de simulation en TypeScript** (génome, réseau, agent,
environnement, boucle — ~1500 lignes) + **visualisation temps réel dans le
navigateur** (canvas) : agents, raycasts, pommes, HUD, panneau du meilleur agent,
contrôles de vitesse. Interface Next.js / React.

**→ C'est le support de démo idéal** : la simulation tourne *live* dans le
navigateur, sans installation, on voit l'évolution se dérouler en direct.

---

## 7. Ce qui a marché / ce qui n'a pas marché

**A marché ✅**
- Le simulateur complet from-scratch (aucun framework ML), testé, propre.
- L'**instrument de mesure comportementale** (steer probe) — sans lui, tout le
  reste était aveugle.
- L'émergence robuste de fourrage via **repro apple-gated + grande population**.
- Le portage web + visualisation live.

**N'a pas marché (falsifié proprement, documenté) ❌**
- Régler des paramètres pour débloquer l'évolution (rebrasse les seeds).
- Amplifier la mutation (accélère la dérive, aucun neurone caché).
- Le crossover comme amplificateur (c'est un *régularisateur*, il moyenne).
- Enrichir la perception (dimensionnalité → instabilité).
- Démarrer avec un génome sparse (prive les capteurs d'information trop longtemps).

> **Note de posture** : les échecs sont ici des **résultats**, pas des ratés. Chaque
> hypothèse a été falsifiée avec une expérience contrôlée à une variable et
> documentée. C'est ce qui donne du poids à la conclusion.

---

## 8. Répartition du temps & ce qui a coûté le plus cher

| Bloc | Période | Poids relatif | Nature |
|------|---------|---------------|--------|
| Fondations (Phases 1-8) | Juin 9-12 | ~30 % | Ingénierie : construire un simulateur correct et testé |
| **Investigation évolutive (poc2.2)** | Juil 6-7 | **~35 %** | **Le plus dur** : diagnostic, instrumentation, campagne |
| poc2.3 (6 volets) | Juil 7-8 | ~25 % | Science expérimentale : hypothèses, runs, ablations |
| Portage web + viz | Juil 6 | ~10 % | Intégration TypeScript + rendu navigateur |

**Ce qui a pris le plus de temps et d'ingéniosité** :
1. **Construire le bon instrument de mesure.** Le comportement « avoir mangé des
   pommes » ne mesure pas la compétence. Concevoir une sonde qui teste réellement
   l'orientation vers la nourriture a débloqué tout le reste.
2. **Les campagnes multi-seeds.** Chaque conclusion exige plusieurs runs longs
   (15k-30k ticks) sur 3 seeds pour ne pas confondre effet réel et chance de seed.
   C'est lent : ~15-25 ticks/s à pleine population (le raycasting est le goulot).
3. **Résister à la tentation de « croire » un bon résultat** sur un seul seed.

---

## 9. Ce qui est le plus difficile dans ce projet — et pourquoi

1. **Mesurer l'intelligence, pas l'activité.** Le piège central : un agent peut
   accumuler des pommes par hasard sans stratégie. Distinguer *compétence* de
   *chance* demande un instrument dédié. → C'est *le* verrou du projet.
2. **Distinguer un vrai effet d'un effet de seed.** L'évolution est stochastique
   et *fondation-dépendante* : le premier génome chanceux colonise la population.
   D'où l'obligation de raisonner sur 3 seeds, ce qui triple le coût de chaque
   test.
3. **Garantir les invariants sous mutation.** Le réseau doit rester feedforward
   quoi qu'il arrive → détection de cycle par DFS avant *chaque* ajout de
   connexion, y compris dans le crossover.
4. **Accepter de revenir en arrière.** Le résultat le plus contre-intuitif : des
   améliorations « évidentes » (plus de capteurs, recombinaison) *dégradent* le
   système. Il faut le mesurer et l'assumer.

---

## 10. Résultats & bilan chiffré

- Simulateur ALife complet, **from scratch**, ~3000 lignes src + ~2000 lignes
  tests, **148 tests verts** (suite complète exécutée), `pylint` 9.93/10, `black` clean.
- **Première émergence robuste** de fourrage : 86 / 84 / 56 % de fourrageurs
  (= proportion d'agents vivants qui s'orientent vraiment vers la nourriture) sur
  les 3 seeds, tenue à 30 000 ticks.
- **6 hypothèses testées** en isolation à une variable, chacune conclue par une
  preuve (4 falsifiées, 2 validées).
- Un **résultat scientifique** net : dans ce régime, seuls les leviers *additifs*
  (population, sélection directe) débloquent l'évolution ; les leviers *réducteurs*
  nuisent, même bien fondés théoriquement.
- Un **portage web** rendant la simulation observable en direct dans le navigateur.

**Message de clôture (30 s)** : on n'a pas *programmé* un comportement de chasse —
on a construit les conditions pour qu'il **émerge**, on a appris à le *mesurer*
honnêtement, et on a cartographié ce qui le fait apparaître (et ce qui le tue).

---

## Annexe — proposition de plan de slides (10 min)

| # | Slide | Durée | Contenu | Démo |
|---|-------|-------|---------|------|
| 1 | Titre + le projet en 1 phrase | 0:30 | Intention : faire *émerger*, pas entraîner | |
| 2 | La boucle de vie d'un agent | 1:00 | Percevoir → décider → agir → manger → repro → mourir | |
| 3 | **DÉMO live** | 1:30 | Simulation navigateur qui tourne | ▶️ |
| 4 | Les fondations (archi + invariants) | 1:00 | From scratch, testé, feedforward, YAML | |
| 5 | Le problème : « ça survit mais n'apprend pas » | 1:00 | La population est stable — mais fourrage-t-elle vraiment ? Invisible à l'œil nu | |
| 6 | La clé : construire le bon instrument de mesure | 1:30 | Sonde de fourrage — définir « fourrageur » et « % », puis la révélation : le champion à −0,17, sous le hasard | |
| 7 | La percée : changer le mécanisme (repro apple-gated + pop) | 1:30 | Tableau 86/84/56 % — émergence robuste | |
| 8 | Ce qu'on a testé et falsifié (6 volets) | 1:00 | Le résultat : seuls les leviers additifs marchent | |
| 9 | Conclusion + difficultés + ouverture | 0:30 | Émerger, mesurer, cartographier | |

**Conseils de répartition** : accorder le plus de temps aux slides 6-7
(instrument de mesure + percée) — c'est là qu'est l'ingéniosité. **Le vocabulaire
(fourrageur, % de fourrageurs, seed) se définit naturellement sur la slide 6**,
juste avant de montrer les chiffres — pas besoin d'une slide glossaire séparée
dans un format 10 min. Intro et conclusion 30 s chacune. Slides sans texte long :
une idée + un visuel/chiffre.
