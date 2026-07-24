# 03 — Fondations (Phases 1-8) : le socle technique

> Le simulateur ALife construit *from scratch*, phase par phase, avec tests à
> chaque étape (master → poc2.1, juin 2026). Ce chapitre décrit **l'architecture**
> sur laquelle tout le reste s'appuie. Sources : `docs/Phase/Phase1-8`, `README.md`,
> les invariants de `CLAUDE.md`.

---

## Intention

Poser un écosystème artificiel **entièrement maîtrisé** : chaque brique (génome,
réseau, agent, monde, boucle) écrite à la main, testée, pilotée par config. Aucun
framework ML (contrainte d'origine, cf. `01`). L'objectif de cette phase n'est pas
encore l'évolution adaptative — c'est d'avoir un simulateur **correct,
déterministe et instrumentable**.

---

## Ce qui a été fait — les 8 phases

| Phase | Livré | Fichier(s) |
|---|---|---|
| **1** | Config typée (dataclasses `SimConfig`) + `default.yaml` — **zéro nombre magique** | `config.py`, `config/default.yaml` |
| **2** | Génome NEAT : `NodeGene` / `ConnectionGene`, 5 mutations, DFS anti-cycle, compteur d'innovation global | `genome.py` |
| **3** | Réseau feedforward : tri topologique **caché à l'init**, forward pass, normalisation des sorties | `network.py` |
| **4** | Environnement : pommes (spawn zone safe, respawn différé), zone de pénalité à gradient | `environment.py`, `apple.py` |
| **5** | Agent : raycasts (16 rayons, first-hit), énergie (drain/tick, manger, repro, mort), cycle de vie complet | `agent.py` |
| **6** | Simulation : boucle fixed-timestep (découplée du rendu), gestion population, extinction propre, logging CSV continu, sauvegarde du meilleur génome | `simulation.py` |
| **7** | Rendu Pygame **séparé de la logique** : agents, pommes, zone pénalité, HUD, raycasts visibles, gradient d'énergie | `renderer.py` |
| **8** | Intégration : `main.py` CLI (`--mode visual/headless`, `--seed`, `--ticks`, `--config`), indicateur de fin de vie | `main.py` |

---

## Détail architectural par brique

### Le génome (Phase 2)
- Encodage NEAT : une liste de **gènes de nœuds** et de **gènes de connexions**,
  chacun avec un **numéro d'innovation** (identité historique globale, sert à
  aligner deux génomes pour le crossover).
- Fondateur : **fully-connected** (toutes les entrées reliées aux 2 sorties). Ce
  choix aura des conséquences fortes plus tard (cf. `05` : plus d'inputs = plus de
  connexions initiales = plus de surface de mutation = moins de robustesse).
- **5 mutations** : `add_node` (split d'une connexion), `add_connection` (avec
  vérification DFS anti-cycle), `remove_node`, `remove_connection`,
  `mutate_weights`. Les taux vivent tous en config (`genome.*_rate`).
- **Garantie feedforward** : la DFS dans `add_connection` refuse toute arête qui
  créerait un cycle. Invariant critique — jamais de récurrence (cf. `01` §4).

### Le réseau (Phase 3)
- Construit une fois : **tri topologique calculé et mis en cache à l'init** de
  l'agent, jamais recalculé pendant sa vie (invariant n°4).
- Forward pass strictement feedforward → **fonction pure et déterministe** de ses
  entrées. C'est la base du déterminisme de tout le simulateur (cf. `11`).
- Sorties normalisées via `tanh ∈ (−1,1)`, puis post-traitement égocentrique.

### L'environnement (Phases 4-5)
- **Pommes** : spawn uniquement dans la **zone safe** (invariant n°6), respawn
  **différé** après consommation (file de respawn).
- **Zone de pénalité murale** : `penalty = zone_max_drain × (1 − dist_mur /
  zone_width)`, appliquée si `dist_mur < zone_width` — **gradient, pas binaire**.
- **Agent** : perçoit par **16 raycasts** first-hit (distance + type d'objet),
  décide via son réseau, agit en égocentrique, mange par contact, dépense de
  l'énergie par tick, se reproduit et meurt (famine ou vieillesse `max_age`).

### La boucle (Phase 6)
- **Fixed-timestep**, découplée du rendu : la sim peut tourner **headless** pour
  les campagnes en masse (invariant n°7).
- Énergie comptée **par tick**, jamais par frame (invariant n°2).
- Logging CSV continu (7 colonnes à l'origine → 26 après l'instrumentation de
  poc2.4, cf. `06`).
- Extinction propre : une population peut légitimement s'éteindre (l'ALife
  n'impose pas de plancher — le `population.min_size` sera d'ailleurs retiré en
  poc2.3 comme vestigial).

### Le rendu & la CLI (Phases 7-8)
- `renderer.py` est un **observateur pur** : `simulation.py` ne touche jamais
  Pygame. Les raycasts affichés sont **reconstruits** depuis `Agent.sense()`, zéro
  accès à l'état privé.
- `main.py` : deux modes, `visual` (Renderer interactif) et `headless` (boucle +
  progression + CSV). Overrides CLI par-dessus le YAML.

---

## Résultats de la phase fondation

- Simulateur **fonctionnel et déterministe**, testé phase par phase (114 tests à
  la clôture de poc2.1/début poc2.2, pylint 10/10).
- Équilibrage énergétique et calibration de la zone de pénalité faits en poc2.1
  (`daa8db2`, `7e3d32a`).
- **La population survit** — mais c'est précisément là que commence le vrai
  problème scientifique : *elle survit sans apprendre à fourrager*. C'est le point
  de départ de poc2.2 (`04`).

---

## Diagnostic / ce que cette phase a révélé

Le socle est sain, mais il expose d'emblée la tension centrale du projet : un
simulateur *viable* n'est pas un simulateur *adaptatif*. Trois propriétés du socle
vont conditionner tout le reste :
1. le **génome fondateur fully-connected** → surface de mutation large ;
2. le **réseau figé pendant la vie** → tout apprentissage passe par la
   reproduction, jamais par l'expérience (jusqu'à la tentative Hebbienne de `09`) ;
3. la **survie quasi gratuite** → le fourrage est à peine sélectionné.

## Verdict

Fondations livrées, correctes, instrumentables. Le simulateur est prêt ; la
question « pourquoi ça n'évolue pas ? » peut être posée proprement. → `04`.
