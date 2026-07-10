# Plan d'implémentation — ALife Neuroevolution

## Phase 1 — Fondations ✅
- [x] config.py (SimConfig dataclass + chargement YAML)
- [x] config/default.yaml (tous les paramètres)
- [x] tests/test_config.py

## Phase 2 — Génome ✅
- [x] NodeGene, ConnectionGene
- [x] Genome (init fully connected 33×2, clone, sérialisation JSON)
- [x] Innovation counter global
- [x] 5 mutations (add_node, add_connection avec DFS, remove_node,
        remove_connection, mutate_weights)
- [x] tests/test_genome.py (mutations valides, pas de cycle, IDs uniques)

## Phase 3 — Réseau de neurones ✅
- [x] Topological sort (cache à l'init)
- [x] Forward pass feedforward
- [x] Normalisation output vitesse
- [x] tests/test_network.py (forward déterministe, cycle détecté)

## Phase 4 — Environnement ✅
- [x] Apple (spawn zone safe, respawn aléatoire)
- [x] Zone pénalité gradient
- [x] tests/test_environment.py (pommes hors zone penalty, gradient correct)

## Phase 5 — Agent ✅
- [x] Raycasts (16 rays, first-hit, (distance, type))
- [x] Énergie (drain/tick, manger, reproduction, mort)
- [x] Cycle de vie complet (naissance, reproduction, mort famine/vieillesse)
- [x] tests/test_agent.py

## Phase 6 — Simulation (boucle principale) ✅
- [x] Fixed timestep loop (découplé rendu)
- [x] Gestion population (spawn, mort, extinction propre)
- [x] CSV logging continu
- [x] Sauvegarde meilleur génome
- [x] tests/test_simulation.py (tick order, CSV produit)
- [x] Respawn différé des pommes (patchs rétro Phase 4/5, CDC §5.2)
- [x] CSV logger exposé en API publique (open_csv_logger / close_csv_logger) → Phase 8

## Phase 7 — Rendu ✅
- [x] Renderer Pygame (agents, pommes, zone penalty, HUD)
- [x] Raycasts visibles (reconstruits depuis Agent.sense(), zéro accès privé)
- [x] Gradient couleur énergie (rouge→jaune→vert) + UI boutons vitesse
- [x] tests/test_renderer_smoke_500_ticks_with_ui.py (5 tests, SDL dummy)
- [x] Mode headless (renderer.py non instancié) → livré Phase 8 (main.py CLI)
- [x] Indicateur visuel fin de vie (end_of_life_ticks derniers ticks) → livré Phase 8

## Phase 8 — Intégration ✅
- [x] main.py (CLI argparse : --mode/--seed/--ticks/--config, fallback YAML)
- [x] Mode visual (Renderer) + mode headless (boucle + progress + CSV)
- [x] Indicateur fin de vie (override gradient → rouge, piloté par config)
- [x] tests/test_main_cli_modes.py (9 tests : modes, overrides, déterminisme)
- [x] PHASE8.md (architecture + décisions)

## Phase 9 — AWS + Dashboard ⬜
- [ ] S3 (upload ZIP + génomes)
- [ ] DynamoDB (métriques)
- [ ] Amplify (dashboard)

## Branche poc2.2 — Dynamique évolutive (investigation) ✅
> POC hors numérotation des phases : rendre l'évolution *adaptative*, pas seulement
> viable. Journal complet dans `docs/Audits/AUDIT-poc2.2-v3.md` (ÉTAPES 0–10).
- [x] Instrumentation évolutive (spéciation, 6 colonnes CSV, sondes
        `tools/steer_probe.py` + `tools/run_and_probe.py`)
- [x] 5 correctifs architecturaux dc20330 (égocentrisme B3a, input 2D 49, fécondité
        ∝ énergie B3b, élitisme, clamp poids I2) → règlent la **viabilité**
- [x] Diagnostic (audit v3) : blocage = sélection ≪ mutation + dérive, PAS le repère
        de sortie. Preuve = sonde comportementale (champion anti-fourrageur r=−0,17)
- [x] Campagne leviers (mutation / drain / max_energy / food / move_cost) : aucun
        réglage paramétrique ne robustifie — chaque régime rebrasse quel seed gagne
- [x] Changement **structurel** `agent.apples_per_offspring` (défaut 0.0 = legacy ;
        >0 = fécondité ∝ pommes cumulées) + `agent.move_cost`
- [x] Résultat : `config/apple_repro_bigpop.yaml` = 1ʳᵉ émergence de fourrage
        **robuste (3 seeds) ET stable (30k)** : 86/84/56 % fourrageurs
- [x] Décision : promouvoir `apple_repro_bigpop` en défaut ? → **OUI**, tranché en
        poc2.3 volet 5 (voir ci-dessous) après l'ablation du capteur 67.
- [ ] ⬜ Validation élargie (N seeds) + réglage de K pour remonter seed 123 (toujours
        le plus faible du trio, 42-56 % selon le run — piste ouverte si besoin de plus
        de perf)

## Branche poc2.3 — Capteurs 67 + visualisation + relance structurelle ✅
> POC hors numérotation. Journal complet dans `docs/Audits/AUDIT-poc2.3.md`.
- [x] Capteurs 67 inputs : apple_dist/wall_dist séparés (4 canaux/rayon),
        proprioception (actual_speed), apples_in_view (fa2656e)
- [x] Panneau réseau (touche N) : nœuds par groupe sensoriel, connexions par
        signe de poids, titre `hidden:N` — évolution structurelle observable
- [x] Sparkline forage rate, HUD 3 lignes (Repro/Gen), fullscreen F11
- [x] Expérience relance structurelle (add_node_rate 0,25 / apples_per_offspring
        3,0, pop défaut) : **falsifiée**. Run `logs/2026-07-07_142103` 30k →
        0 neurone caché, record_apples fige à 53, dérive neutre (gen_dist ×34,
        51 espèces). Le levier poc2.2 était la **population** (bigpop 200→400),
        pas le taux de mutation. `config/default.yaml` remis à l'état canonique.
- [x] Relance par **mécanisme** = crossover NEAT intra-espèce (`68305c2`) :
        `Genome.crossover` (aligné par innovation, enfant feedforward garanti),
        `genome.crossover_rate` (défaut 0.0), `_pick_mate` intra-espèce. 5 tests,
        148 verts, pylint 10/10.
- [x] Campagne crossover 3 seeds / 30k (audit poc2.3 volet 3) : à **pop identique**,
        le crossover améliore fortement 2/3 seeds (42 : 4→88 % ; 7 : 58→96 %) et
        fait passer la moyenne population de −0,08 à +0,19 — **mais régresse sur
        seed 123** (28→10 %). **Non robuste au sens strict** (pas de 3/3 positifs
        comme apple_repro_bigpop) : rebrasse partiellement les seeds. Enseignement :
        les neurones cachés ne discriminent PAS (présents partout, 0,5–1,3).
- [x] Piste (a) **crossover + bigpop** (audit poc2.3 volet 4, `lever_crossover_bigpop.yaml`,
        3 seeds / 30k, `logs/2026-07-08_crossover_bigpop/`) : **FALSIFIÉE**. 51/69/26 %,
        seed 123 encore négatif. La combinaison **sous-performe chaque levier seul**
        (seed 42 : bigpop 76 % vs combiné 51 %). Enseignement : le crossover est un
        opérateur **moyennant** (rapproche tous les seeds de ~50 %, réduit la variance
        inter-seeds), pas amplifiant → seule la **taille de pop** lève tous les seeds.
- [x] Pistes restantes (b) crossover_rate plus bas / (c) N seeds : abandonnées, même
        régime d'homogénéisation que la piste (a) falsifiée. `default.yaml` reste
        `crossover_rate 0.0`.
- [x] **Volet 5 — verdict final capteur, priorité performance** (audit poc2.3 volet 5) :
        le capteur 67 (volet 1) **casse la robustesse** (seed 123 : 43 %→1 %), aucun
        canal isolé n'est coupable (ablation split/proprio/apples_in_view) — c'est la
        **dimensionnalité d'entrée** (génome fully-connected plus large = plus de
        surface de mutation). Capteur devenu **configurable**
        (`sensors.split_distance/proprioception/apples_in_view`, zéro nombre magique,
        `SensorConfig.num_inputs` dérivé). **`config/default.yaml` PROMU** au package
        complet `apple_repro_bigpop` (monde ×√2, agents/pommes plus gros, mutation
        0,15, `apples_per_offspring 3.0`, pop 200/400, capteur **49 legacy**) — 3/3
        seeds robustes (86/77/42 % à 15k, cohérent avec l'étalon 86/84/56 à 30k). 152
        tests verts, black clean, pylint stable. Décision poc2.2 (ligne ci-dessus)
        close : le package apple_repro_bigpop **est** le nouveau défaut.
- [x] **Volet 6 — génome fondateur sparse** (audit poc2.3 volet 6, `genome.
        initial_connectivity`, `lever_sparse_init.yaml`) : **FALSIFIÉ, plus lourdement
        que toutes les pistes précédentes**. Hypothèse : démarrer sparse (~5
        connexions/output au lieu de 49) réduirait la surface de mutation identifiée
        au volet 5. Résultat 3 seeds / 15k : **86→6 %, 77→59 %, 42→7 %** — dégrade
        TOUS les seeds, y compris la cible seed 123 (steering −0,373, pire chiffre de
        toute la campagne). La plupart des capteurs restent débranchés trop
        longtemps ; le fully-connected agissait comme filet de sécurité perceptif.
        `initial_connectivity` reste à 1.0 (implicite) dans `default.yaml`. 155 tests
        verts, black clean, pylint stable. Mécanisme + config gardés comme référence.

## Branche poc2.4 — Perf de simulation + nouveauté (1er levier positif) ✅
> Débit de simulation (pour la boucle de recherche) + reprise recherche.
> Détails : `docs/DESIGN-poc2.4-perf.md`, `docs/RESULTS-novelty.md`.

- [x] **Levier perf 1 — campagnes multi-seeds en parallèle** (`tools/campaign.py`,
        `ProcessPoolExecutor`) : chaque seed = `Simulation` indépendante → **×2,64**
        sur 3 seeds, résultats bit-identiques (déterminisme préservé). Zéro
        changement de la simulation.
- [x] **Levier perf 2 — perception batchée NumPy** (`src/agent.py::batch_sense`,
        tick « geler puis percevoir ») : perception de toute la population en une
        passe NumPy. Équivalence **bit-à-bit** avec `sense()` par agent (49 et 67),
        **×1,71** end-to-end (58→100 ticks/s), combiné L1+L2 **×4,0**. Le forward
        pass NEAT hétérogène devient le plafond (45 % du tick, non batchable).
- [x] **Chantier recherche n°3 — bonus de nouveauté additif** (novelty search,
        Lehman & Stanley 2011 ; `src/novelty.py`, `NoveltyConfig`) : **1er levier
        NON falsifié du projet**. Campagne 6 seeds/15k : moy **52 %→62 % (+10)**,
        chaque seed monte ou tient, aucun ne régresse (contraire des réducteurs).
        Additif (ne pénalise jamais). Sweep de `weight` → optimum franc à **1.0**.
- [x] **Optim perf nouveauté** — `novelty.recompute_interval` amortit le scoring
        O(pop²) sur N ticks. Balayage 1/10/25 → moy 62/62/60, débit 71/113/122
        ticks/s. **interval=10** = plein gain au débit de base.
- [x] **PROMU en `default.yaml`** : `novelty {enabled:true, weight:1.0, neighbors:15,
        recompute_interval:10}` — meilleur défaut jamais atteint (moy 62 % vs 52 %).
        Section YAML optionnelle → configs antérieures inchangées. 168 tests verts,
        pylint 10/10, app réelle vérifiée end-to-end.
- [x] **Piste archive de nouveauté — FALSIFIÉE** (`novelty.archive_enabled`,
        `config/lever_novelty_archive.yaml`, injection aléatoire p=0,01, Lehman &
        Stanley 2011) : campagne 6 seeds/15k, moy **62 %→55 % (−7)**. Régresse
        4/6 seeds (42 : 86→75 ; 7 : 91→73 ; 123 : 55→42 ; 99 : 25→18), n'aide
        qu'à la marge 2/6 (1 : 27→32 ; 5 : 87→89) — et PAS le seed qu'elle
        visait le plus (99, le pire en absolu, régresse). Diagnostic : élargir
        le voisinage avec des comportements obsolètes dilue le signal de
        nouveauté vis-à-vis de la pression de sélection courante — même
        symptôme « moyennant » que crossover/capteur 67/sparse/fitness sharing,
        malgré une construction additive. **5ᵉ mécanisme réducteur falsifié**,
        1ᵉʳ qui déguise un effet réducteur sous une forme additive. Mécanisme
        gardé câblé (`archive_enabled: false` par défaut), non promu. 174 tests
        verts, black clean, pylint stable.