# 02 — Chronologie git : la carte temporelle du projet

> Analyse directe du dépôt, **restreinte à la chaîne `master → poc2.x` + `poc3`**
> (voir §0 : le dépôt distant est partagé et contient d'autres histoires, hors
> périmètre). Toutes les dates en ISO, fuseau indiqué quand il est significatif.

---

## 0. ⚠️ Périmètre : le dépôt distant est PARTAGÉ

Le remote `origin` (`github.com/baweuh/pa4iabd`) est le dépôt **du groupe**, pas
celui de ce travail. Il contient **six histoires git indépendantes** (six commits
racines sans parent commun), poussées par trois personnes différentes. Elles ne
sont pas des variantes d'un même projet : elles n'ont **aucun ancêtre commun** et
n'ont jamais été fusionnées.

**Seule la chaîne `master → poc2.1 → … → poc2.6` (+ la latérale `poc3`) relève de
ce travail.** Elle représente **106 commits, tous authorés `r-palmier`**, et ne
contient aucun fichier provenant des autres histoires (vérifié). Les autres refs
présentes dans un clone (`origin/main`, `origin/web-integration`,
`origin/update-web`, `origin/poc2.4-web-integration` — 10 commits au total) sont
le travail d'autres personnes sur d'autres sujets ; **ce corpus ne les documente
pas et ne s'en réclame pas.**

> Elles apparaissent malgré tout dans un `git branch -a` local parce que le
> refspec de fetch par défaut (`+refs/heads/*:refs/remotes/origin/*`) rapatrie
> toutes les branches du remote. C'est un artefact de configuration git, pas un
> lien de parenté.

---

## 1. Chiffres d'ensemble (périmètre de ce travail uniquement)

- **106 commits** sur la chaîne `master → poc2.x` + `poc3`, **100 % `r-palmier`**.
  (Un `git rev-list --all --count` sur le dépôt partagé renvoie 116 : il compte
  les 10 commits des autres histoires — voir §0.)
- **Empan** : 2026-06-09 → 2026-07-24, soit **~1,5 mois** de travail effectif.
  - Premier commit de ce travail : `92c7c32` « initial », 2026-06-09 10:47.
  - Dernier commit de science : `db3dc19` sur `poc2.6`, 2026-07-22 13:39 (audit
    de clôture) ; le présent corpus documentaire suit le 2026-07-24 (cf. §7).

---

## 2. Topologie des branches

L'histoire est une **chaîne quasi-linéaire de branches « preuve de concept »** :
chaque `poc2.x` part de la précédente, emporte tout l'historique antérieur,
travaille un jeu d'hypothèses, puis se clôt. Les compteurs de commits sont donc
**cumulatifs** le long de la chaîne.

```
master → poc2.1 → poc2.2 → poc2.3 → poc2.4 → poc2.5 → poc2.6   (tronc principal)
                                                  └── poc3       (branche parallèle, abandonnée)
```

- **Tronc** : `master` → `poc2.1` → … → `poc2.6` (HEAD actuel).
- **`poc3`** est une branche **latérale** partant du *premier* commit de poc2.6
  (`e2cb60a`, 2026-07-16), **pas** de la pointe de poc2.6. Elle a tourné en
  parallèle et a été close le 2026-07-20.
- **`origin/poc2`** (racine `ae2a25e`, 2026-06-09) est une seconde racine
  `r-palmier` : les Phases 1-2, fusionnée dans `master` par `fa152f8`. Elle
  appartient bien à ce travail. Un `refs/stash` traîne près de la racine de
  master.
- Les autres refs du dépôt partagé **ne sont pas des branches de ce travail** et
  ne figurent pas dans ce graphe (cf. §0).

**Commits cumulés par pointe de branche :**

| Branche | Commits (cumulés) | ~Nouveaux sur la branche | Période |
|---|---|---|---|
| master | 7 | 7 (fondations) | 2026-06-09 → 06-10 |
| poc2.1 | 17 | ~10 | 2026-06-10 → 06-11 |
| poc2.2 | 26 | ~9 | 2026-06-11 → 07-07 |
| poc2.3 | 52 | ~26 | 2026-07-07 → 07-10 |
| poc2.4 | 79 | ~27 | 2026-07-10 → 07-15 |
| poc2.5 | 88 | ~9 | 2026-07-15 → 07-16 |
| poc2.6 | 97 | ~9 | 2026-07-16 → 07-22 |
| poc3 | 93 | 4 (depuis la racine poc2.6) | 2026-07-16 → 07-20 |

---

## 3. Backbone daté — première et dernière commit par branche

**master** — 2026-06-09 → 2026-06-10
Échafaudage + premières phases moteur. `fe8ffbe` (init projet) → `ec3ac99`
(« Phase 1 — config.py + default.yaml + tests »). Gelée très tôt ; tout le vrai
travail continue sur les branches poc.

**poc2.1** — 2026-06-10 → 2026-06-11
La branche « faire tourner ». Construit le simulateur de bout en bout : réseau
(Phase 3), environnement + pommes (Phase 4), agent (Phase 5), boucle de sim
(Phase 6), CLI (Phase 8). Pointe : `7e3d32a` « logging par run + équilibrage
énergie + README ».

**poc2.2** — 2026-06-11 → 2026-07-07
La dynamique évolutive rendue réelle. `5b8458f` (audit invariants + 4 fixes) →
`b791b0b` (mise en ordre). **Note : une pause de ~3 semaines** (2026-06-12 →
2026-07-06) — le projet s'arrête puis reprend. Culmine sur `009f2dc` (ÉTAPE 10 :
repro ∝ pommes cumulées = 1ʳᵉ émergence robuste+stable).

**poc2.3** — 2026-07-07 → 2026-07-10
Perception enrichie + viz réseau + relances structurelles. `fa2656e` (capteurs
67) → `cf4a1e2` (audit de tuyauterie). Crossover, fitness sharing, sparse,
capteur 67 — résultats mitigés, plusieurs falsifications, capteur 49 promu.

**poc2.4** — 2026-07-10 → 2026-07-15
**La branche la plus productive (~27 commits).** Campagnes systématiques de
falsification. `702bc17` (design perf) → `234fc6e` (cleanup post-audit). Contient
les 3 leviers promus (novelty, densité, K-sweep) et 5 falsifiés (biais, archive,
critère minimal, troncature, îles), plus l'instrumentation et les correctifs de
bugs.

**poc2.5** — 2026-07-15 → 2026-07-16
HyperNEAT / encodage indirect, V1 → V4. `2f217f0` (MVP) → `658389b` (V4, chantier
clos). Chaque variante falsifiée, honnêtement documentée. Une impasse de
recherche.

**poc2.6** — 2026-07-16 → 2026-07-22 (HEAD actuel, dernière branche)
Sigma auto-adaptatif + plasticité Hebbienne V1/V2, tous falsifiés au diagnostic.
`e2cb60a` (ouverture) → `db3dc19` (audit de clôture). Branche close **sans
verdict positif**, suivie de deux audits croisés (cohérence + traçabilité).

**poc3** — 2026-07-16 → 2026-07-20 (branche latérale)
Expérience d'échelle : topologie fixe + forward pass batché, `batch_eat`, cap du
pool de novelty, pour atteindre des milliers d'agents. `0311857` (topologie fixe)
→ `f6aee15` (clôture, campagne d'échelle non concluante). **Close comme
inconclusive**, abandonnée définitivement le 2026-07-22.

---

## 4. L'arc narratif en une ligne

> Construire le simulateur (master / poc2.1) → faire émerger le fourrage évolutif
> (poc2.2) → enrichir perception + évolution structurelle (poc2.3) → campagnes
> rigoureuses de falsification sur les leviers de sélection / novelty / échelle
> (poc2.4, le pic) → explorer l'encodage indirect (poc2.5, impasse) et la grande
> échelle à topologie fixe (poc3, inconclusive) → sonder les règles
> d'apprentissage : mutation auto-adaptative + plasticité Hebbienne (poc2.6, tous
> falsifiés, branche close avec audits).

Un **journal de recherche piloté par la falsification**, où la plupart des
hypothèses ont été réfutées et où seule une poignée de leviers (bonus de
nouveauté, K-sweep, densité, population) a été promue en défaut.

---

## 5. Commits-clés commentés

> Sélection des commits structurants (au-delà de la liste exhaustive du
> `SYNTHESE.md §7`). Utile pour naviguer le dépôt.

**Fondations**
- `ec3ac99` (06-10) — Phase 1 : config typée + default.yaml. Le socle « zéro
  nombre magique ».
- `dc20330` (06-12) — poc2.2 : **5 améliorations architecturales** (égocentrisme
  B3a, input 2D 49, fécondité ∝ énergie B3b, élitisme, clamp poids I2). Le
  correctif qui règle la *viabilité*.

**La percée**
- `009f2dc` (07-07) — poc2.2 ÉTAPE 10 : repro ∝ pommes cumulées → **1ʳᵉ émergence
  robuste + stable**. Le commit fondateur du reste du projet.

**poc2.3**
- `fa2656e` (07-07) — capteurs 67 + proprioception + viz réseau (+ défaut
  apple_repro 5.0).
- `68305c2` (07-08) — crossover NEAT intra-espèce.
- `7851137` (07-08) — capteur configurable + **promotion du package 49-inputs en
  défaut** (volet 5).
- `442256f` (07-08) — génome sparse, falsifié.
- `fd84a1c` (07-09) — **raycast vectorisé NumPy** + cache pommes (+25 %).

**poc2.4 (le pic)**
- `702bc17` / `900bcb2` (07-10) — les 2 leviers perf (campagnes parallèles ×2,64 ;
  perception batchée NumPy ×1,71).
- `6b18bc1` / `eaf6e72` (07-10) — **novelty search**, 1er levier NON falsifié,
  promu en défaut.
- `6ef2938` / `3ba8df3` (07-10) — nœud de biais, **pire régression** (−34).
- `21c82a6` (07-10) — fix freeze ~100 ticks (mean_pairwise_distance vectorisée,
  318→39 ms).
- `b3b4afc` (07-10) — **densité** (carte ×√2 + vitesse ÷2) promue en défaut.
- `6f634ab` (07-15) — **K-sweep** (`apples_per_offspring` 3.0→1.5), meilleur
  résultat net du projet.
- `5c7c0ba` (07-15) — modèle d'îles (falsifié) + instrumentation étendue.
- `f070f64` (07-15 16:16) — **le fix de traçabilité** : `tools/campaign.py`
  n'activait jamais le CSV logger. Sépare l'« avant » (résultats non tracés) de
  l'« après » (voir `11`).
- `c25263b` (07-15) — audit code : fuite mémoire + cache steer_score.

**poc2.5**
- `2f217f0` / `5999b92` (07-15) — HyperNEAT MVP + `trace_lineage.py`.
- `fe58603` → `658389b` (07-15/16) — V1 → V4, chantier clos.

**poc3 (parallèle)**
- `0311857` (07-16) — topologie fixe + forward pass batché.
- `c94c4db` (07-16) — `batch_eat` + `novelty.max_pool_size` (débloque l'échelle).
- `f6aee15` (07-20) — clôture, campagne d'échelle non concluante.

**poc2.6**
- `5e32408` / `e3a4eff` (07-20) — sigma ES, falsifié au diagnostic.
- `86aaefe` / `aa19ae7` / `1001faf` (07-20/21) — Hebbien V1 → V2, falsifié.
- `80cf956` / `db3dc19` (07-21/22) — **les deux audits de clôture** (cohérence
  documentaire + traçabilité scientifique).

---

## 7. Note de provenance — le corpus `HISTORIQUE/` lui-même

Ce corpus (`docs/HISTORIQUE/*.md`, 12 fichiers) a été **rédigé le 2026-07-23**,
mais son commit a été **interrompu par un bug de session** avant l'étape
`git add`/`commit` : les 12 fichiers sont restés *untracked* (`git status`)
pendant ~24h, jusqu'à leur détection et leur commit le **2026-07-24**. Vérifié
fichier par fichier avant de committer : les 12 se terminent sur un verdict
complet (aucune coupure, aucun contenu perdu ou modifié entre rédaction et
commit).

Deux dates à distinguer pour ce corpus précis : **rédaction 2026-07-23**,
**commit 2026-07-24**. Le dernier commit de contenu scientifique (`db3dc19`,
audit de clôture poc2.6) reste daté du 2026-07-22 — c'est lui qui fait foi pour
la chronologie de la recherche relatée dans les chapitres `03`-`10` ; ce
paragraphe documente uniquement la méta-doc qui l'emballe, pas la science
elle-même.
