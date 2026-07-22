# ALife — Neuroevolution Simulation

Un écosystème artificiel où des agents apprennent à **survivre par évolution**,
sans aucun framework de machine learning. Chaque agent est piloté par un petit
réseau de neurones dont la structure et les poids évoluent de génération en
génération — façon NEAT, mais réécrit à la main en Python pur.

---

## Le but

Faire émerger un **comportement intelligent à partir de la sélection naturelle**,
pas de l'entraînement supervisé. On ne dit jamais à un agent quoi faire : on lui
donne des yeux (raycasts), un cerveau (réseau de neurones) et une contrainte
vitale (l'énergie). Ceux qui trouvent les pommes et évitent les murs se
reproduisent ; les autres meurent. Au fil des générations, des stratégies de
chasse et d'évitement apparaissent toutes seules.

**La boucle de vie d'un agent :**

- **Percevoir** — 16 raycasts à 360° renvoient ce qu'ils touchent → **49 entrées**
  du réseau : 16 distances normalisées, 16 drapeaux « pomme », 16 drapeaux
  « mur », plus l'énergie de l'agent. (Le layout est configurable, `num_inputs`
  est dérivé des toggles `sensors.*` — jamais codé en dur.)
- **Décider** — le réseau feedforward produit 2 sorties → un vecteur vitesse.
- **Agir** — l'agent se déplace, consomme de l'énergie à chaque tick.
- **Manger** — une pomme rend de l'énergie. La zone près des murs en draine
  (gradient de pénalité).
- **Se reproduire** — au-dessus d'un seuil d'énergie, l'agent clone son génome
  avec mutations (poids, ajout/suppression de nœuds et connexions).
- **Mourir** — de faim (énergie à 0) ou de vieillesse (âge max).

## Pourquoi on l'a fait

- **Comprendre la neuroévolution de l'intérieur** : pas de `neat-python`, pas de
  PyTorch, pas de Gym. Tout est codé à la main — génome, topological sort,
  forward pass, mutations — pour vraiment saisir la mécanique.
- **Un terrain de jeu pour l'émergence** : observer en direct des comportements
  non programmés apparaître par pression de sélection.
- **Un projet d'ingénierie propre** : architecture stricte, invariants
  documentés, tests à chaque module, séparation logique / rendu.

## Comment c'est construit

Architecture modulaire, chaque brique testée isolément (voir `PLAN.md` pour
l'avancement phase par phase) :

| Module | Rôle |
|---|---|
| `src/config.py` + `config/default.yaml` | Toute la configuration (invariant : **zéro valeur hardcodée**) |
| `src/genome.py` | Génome NEAT-like : nœuds, connexions, 5 mutations, sérialisation JSON |
| `src/network.py` | Réseau feedforward : topological sort (caché à l'init), forward pass |
| `src/agent.py` | Capteurs (raycasts), énergie, cycle de vie |
| `src/environment.py` + `src/apple.py` | Monde, pommes, zone de pénalité murale |
| `src/simulation.py` | Boucle principale (fixed timestep), population, logging CSV |
| `src/renderer.py` | Rendu Pygame (agents, pommes, raycasts, HUD) — **séparé** de la logique |
| `src/main.py` + `main.py` | CLI : mode visuel ou headless |

**Principes clés :** réseau strictement feedforward (détection de cycle par DFS
avant chaque connexion), énergie comptée par *tick* (jamais par frame), et le
moteur de simulation ne touche jamais à Pygame.

Stack : **Python 3.10+, Pygame, NumPy, PyYAML**. Aucun framework ML n'est
utilisé : le génome NEAT, le réseau, la spéciation et la nouveauté sont écrits
à la main (NumPy pour la vectorisation uniquement). La contrainte formelle
« aucun framework ML » a été levée en fin de projet (2026-07-20) sans qu'aucun
n'ait été introduit ; `neat-python` et `gym` restent exclus par choix
scientifique — ce sont des encodages et des environnements RL tout faits, ce
qui viderait le sujet de sa substance.

---

## Installation & premier run — pas à pas

### 1. Prérequis

- Python **3.10 ou plus récent** (`python --version` pour vérifier).
- `git` pour cloner le dépôt.

### 2. Récupérer le projet

```bash
git clone <url-du-repo> alife-neuroevo
cd alife-neuroevo
```

### 3. Créer un environnement virtuel (recommandé)

```bash
python -m venv .venv
source .venv/bin/activate      # Linux / macOS
# .venv\Scripts\activate       # Windows PowerShell
```

### 4. Installer les dépendances

```bash
pip install -r requirements.txt
```

> Sur Linux, Pygame peut nécessiter quelques libs système (SDL). Si l'import
> échoue : `sudo apt install python3-dev libsdl2-dev`.

### 5. Vérifier que tout marche (tests)

```bash
python -m pytest tests/ -v
```

Tous les tests doivent passer avant de lancer la simulation.

### 6. Lancer la simulation

**Mode visuel** (fenêtre Pygame, contrôles de vitesse, HUD) :

```bash
python main.py
```

**Mode headless** (sans rendu, idéal pour calibrer ou faire tourner longtemps) :

```bash
python main.py --mode headless
```

> Note : la fenêtre s'adapte automatiquement à la résolution de ton écran.
> Ferme la fenêtre ou fais `Ctrl+C` (headless) pour arrêter.

### 7. Options utiles

```bash
python main.py --config config/default.yaml      # config custom
python main.py --mode headless --seed 7          # graine RNG reproductible
python main.py --mode headless --ticks 10000     # budget de ticks (0 = sans limite)
```

Toute la simulation se pilote depuis le YAML — taille du monde, vitesse des
agents, drain d'énergie, taux de mutation, etc. Édite `config/default.yaml`
(ou ta copie) plutôt que le code.

### 8. Résultats

Après une exécution, chaque run crée son dossier horodaté dans `logs/` :

- `logs/<run>/metrics.csv` — métriques par intervalle (population, nourriture, ticks).
- `logs/<run>/best_genome.json` — le meilleur génome courant du run, rejouable.
- `logs/<run>/best_agents/agent_NNN_record_X.json` — l'historique des records.

---

## Qualité du code

```bash
black src/ && pylint src/      # formatage + lint (obligatoires avant commit)
python -m pytest tests/ -v     # suite de tests complète
```

## Pour aller plus loin

- `PLAN.md` — feuille de route et avancement : Phases 1 à 9, puis l'investigation
  poc2.2 et les branches de recherche poc2.3 → poc2.6.
- `docs/SYNTHESE.md` — **la vue d'ensemble à lire en premier** : la trajectoire
  complète, ce qui a été promu (4 leviers, tous liés à l'échelle ou à
  l'écologie) et ce qui a été falsifié (13 leviers). Le **§6bis** en donne le
  tableau complet, levier par levier, avec sa convention de comptage.
- `docs/RESULTS-*.md` — un document par levier **promu** (novelty, densité,
  K-sweep) ; `docs/FALSIFIED-*.md` et `docs/DIAGNOSTIC-*.md` — un document par
  levier **écarté**, avec sa campagne et son verdict. C'est là que vivent les
  résultats de recherche.
- **Branche `poc3`** — tentative de valider l'hypothèse d'**échelle** (topologie
  fixe + batching, jusqu'à 16 000 agents). Architecture livrée et mesurée, mais
  l'hypothèse elle-même n'a **jamais été tranchée**, et la branche a été
  **abandonnée** : c'est la limite assumée de ce travail. Voir
  `docs/SYNTHESE.md` §6.

> Note : le fichier `CLAUDE.md` (invariants d'architecture, utilisé comme
> mémoire de l'assistant de développement) n'est **pas versionné** — il
> n'apparaît donc pas dans un clone. Les invariants qu'il porte sont résumés
> dans la section « Architecture » ci-dessus et détaillés dans `PLAN.md`.
- `docs/Phase/PhaseN.md` — documentation post-implémentation de chaque phase.
- `docs/Audits/` — audits darwiniens de la branche poc2.2 (v1, v2, v3). Le v3
  (`AUDIT-poc2.2-v3.md`) est le journal complet de l'investigation évolutive
  jusqu'à l'émergence du fourragement (reproduction ∝ pommes cumulées).
