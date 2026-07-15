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
> **Hors périmètre de Claude — géré par un collègue de Robin.** Ne pas
> attaquer cette phase, même une fois tout le reste clos (convenu 2026-07-15).
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
- [x] ✅ Validation élargie (6 seeds) + réglage de K — repris en poc2.4 (voir
        ci-dessous, chantier « K-sweep »). K=1.5 promu : moyenne 6 seeds/30k
        66→79 %, meilleur résultat net du projet. `docs/RESULTS-k-sweep.md`.

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
- [x] **Piste nœud de biais NEAT — FALSIFIÉE, pire régression du projet**
        (`genome.bias_enabled`, `config/lever_bias.yaml`, source constante 1.0
        câblée à chaque sortie à la genèse comme un input) : campagne 6
        seeds/15k, moy **62 %→28 % (−34)**. Effondrement sur les seeds forts
        (42 : 86→13 ; 7 : 91→13 ; 5 : 87→30), léger mieux sur 2 seeds faibles
        (1 : 27→30 ; 99 : 25→41). Diagnostic : le biais injecte un terme
        constant fort et non situationnel directement dans les 2 sorties dès
        la naissance (poids initiaux tirés dans ±`weight_init_range`, jamais
        annulé par une moyenne d'entrées sensorielles) — ça noie le signal
        réactif (virage/vitesse piloté par les rayons) sous un décalage
        systématique, symptôme proche du volet 5/6 poc2.3 (ajouter une source
        au génome fondateur élargit la surface de mutation initiale et casse
        la robustesse), en pire ici car le signal ajouté est **permanent, pas
        situationnel**. `bias_enabled` reste `false`. Mécanisme gardé câblé +
        testé comme référence (add_connection corrige au passage un bug latent
        de repli sens-inverse). 181 tests verts, black clean, pylint 10/10.
- [x] **Bug freeze ~100 ticks — CORRIGÉ** (signalé par Robin en jeu) :
        `mean_pairwise_distance` (diversité génétique, colonne CSV) tournait en
        pur Python O(pop²), profilé à **318 ms** pour pop≈230 (pire près de
        `population.max_size` 400) — déclenché toutes les `log_interval_ticks`
        (100), bien au-delà du budget d'une frame à 60 ticks/s. `count_species`
        n'était pas concerné (peu d'espèces, déjà rapide). Fix à deux niveaux
        (`src/speciation.py`) : cache `_Profile` par génome pour
        `compatibility_distance`/`assign_species` (plus de dict/set/max
        reconstruits par PAIRE) ; `mean_pairwise_distance` réécrite en NumPy
        (même idée que `batch_sense`/`population_novelty` — peu d'innovations
        distinctes en pratique, ~100-200, donc une matrice dense (pop,
        innovations) est bon marché). **318→39 ms à pop=400 (~8x)**.
        Équivalence numérique (pas bit-exacte, ordre de sommation flottant)
        vérifiée contre une référence indépendante. 182 tests verts.
- [x] **Bug densité agents/pommes — symptôme confirmé, correctif « carte
        agrandie » NON PROMU** (signalé par Robin en jeu, confirme
        [[apple-density-signal]] du 2026-07-09). `tools/apple_capture_probe`
        reconfirme le surpeuplement avec novelty actif (lifetime médiane pomme
        14 ticks/0,23s, 20/160 pommes vivantes en moyenne, 54 % des captures
        non clairement dirigées). `config/lever_bigmap.yaml` rafraîchi (monde
        ×√2, 3200×1800, isolé au SEUL changement vs `default.yaml` actuel) :
        la sonde directe confirme un gain net sur le symptôme lui-même
        (lifetime médiane 14→29 ticks, captures « gratuites » 24 %→12 %,
        dirigées 46 %→56 %) — **mais** la campagne 6 seeds/15k au niveau
        évolutif est mitigée : moy foragers **62 %→57 % (−5)**, 3 seeds
        montent (42:+9, 1:+10, 5:≈stable), 3 régressent (7:−23, 123:−11,
        **99:−11, le pire du lot, celui censé être le plus aidé**). Hypothèse
        mécanistique : `sensors.max_distance` (283 px) n'a **pas** grandi avec
        le monde (×1,41) — les pommes sont statistiquement plus souvent hors
        de portée du raycast, donc moins de signal sensoriel exploitable pour
        apprendre à diriger, ce qui peut annuler le bénéfice de la densité
        réduite. Symptôme réel et mesuré, mais ce correctif précis **non
        promu en l'état** (mean négative, seed le plus faible aggravé).
- [x] **Densité — 2ᵉ levier : carte agrandie + vitesse ÷2 — PROMU EN DÉFAUT**
        (Robin : ralentir les agents pour réduire le *balayage*/tick, pas
        seulement la densité statique ; `config/lever_bigmap_slow.yaml`,
        `max_speed` 4,243→2,122, monde ×√2, `max_size` volontairement
        inchangé — voir note infra). Sonde directe : lifetime médiane pomme
        **14→58 ticks (×4)**, adjacent (capture gratuite) stable 12 %.
        Campagne 6 seeds/15k : moy foragers 62 %→58 % (−4), sous le défaut —
        décision Robin : **valider à 30k avant de trancher** (hypothèse :
        agents plus lents mangent moins/tick, la sélection a besoin de plus
        de temps). **Campagne 30k : l'hypothèse se confirme, le levier passe
        POSITIF** : moy foragers **62 %→66 % (+4)**, 4/6 seeds montent dont un
        gain massif sur le seed historiquement le plus dur (1 : 23→58, +35),
        les 2 seeds les plus faibles du défaut (1, 99) montent tous les deux.
        2/6 régressent modérément (7:−7, 123:−15). **PROMU** : `default.yaml`
        world 2263×1273→3200×1800, `agent.max_speed` 4,243→2,122. Population,
        pommes, capteurs, réseau inchangés. Détails complets, tableaux
        complets des 3 campagnes : `docs/RESULTS-density.md`. 182 tests
        verts, black clean, pylint stable.
        **Note `max_size`** : NON réduit à 200 malgré l'intuition « stabiliser
        la pop plus bas » — poc2.2 ÉTAPES 7-10 ont établi empiriquement
        qu'une population plus PETITE rouvre la dérive fondatrice (variance
        inter-seed énorme, un seed bloqué ~14 %) que la grande population a
        justement corrigée ; `max_size 400` est un des deux piliers du seul
        régime robuste+stable connu (`apple_repro_bigpop`). Pas de file
        d'attente de repro : à chaque tick `slots = max_size − survivants`,
        les morts du tick sont remplacés le tick même par les agents de plus
        haute priorité (énergie ou crédit de fourrage).
- [x] ✅ **Critère minimal de reproduction + bande souple — FALSIFIÉ**
        (2026-07-15, campagne 30k complète). Littérature (Soros & Stanley 2016,
        arXiv:2302.09334) proposait un gate de viabilité durable : agent doit
        TENIR un crédit ≥ `apples_per_offspring` pendant N ticks consécutifs
        avant UN enfant (réfractaire, moins frénétique), + pop flottant sous
        cap souple. Implémentation : `agent.reproduction_min_ticks` (0=legacy),
        `_credit_streak` dans `simulation.py`, config `lever_min_criterion.yaml`
        (min_ticks=1000, max_size=500), 7 tests, 189 verts. Commit `0700645`.
        **Validation 30k (6 seeds)** : ❌
        (a) **Forager% neutre** : défaut 62% → min_criterion 63% (+1, bruit).
            Contre l'objectif « sélection plus stricte ».
        (b) **Variance extrême** : seed 7 chute 84%→32% (−52), seed 99
            s'envole 27%→79% (+52). Échange classique des réducteurs : une seed
            gagne, une autre casse.
        (c) **Population NOT flottante** : tous les seeds terminent 488–500
            (épinglés au cap 500), pas de bande 400-500 comme visé. Objectif
            principal non livré.
        Verdict : 6e mécanisme falsifié, profil identique aux réducteurs (bias,
        archive). `default.yaml` garde `reproduction_min_ticks` absent (=0).
        Détails : `docs/FALSIFIED-min-criterion.md`.
- [x] ✅ **Troncature de sélection adoucie (research-roadmap chantier n°2) —
        FALSIFIÉ, pas de bug, sensibilité chaotique confirmée** (2026-07-15).
        Chantier identifié depuis le 2026-07-08, sauté par hypothèse
        (« probable même échec réducteur »), enfin testé empiriquement. Deux
        implémentations :
        (a) `agent.max_children_per_tick` (0=legacy) : plafond plat d'enfants
            par agent par tick. Sweep 1 seed/10k : cap∈{3,5,8,10} = no-op pur
            (aucun agent ne dépasse jamais 3 enfants/tick sur ce seed) ; cap=1
            → 78%, cap=2 → 80%, tous deux **sous** la baseline 82%.
        (b) `agent.reproduction_round_robin` (false=legacy) : répartition
            réellement breadth-first (`_round_robin_fill` dans
            `simulation.py`) — un enfant par agent par PASSE avant qu'aucun
            agent n'en reçoive un 2ᵉ, mais un agent seul (sans concurrence)
            reçoit quand même tous les slots (passes successives), contrairement
            au plafond plat. Sweep 1 seed/10k : identique bit à bit à cap=1
            (78%), preuve qu'en régime stationnaire (≤1 slot ouvert/tick) tous
            les mécanismes convergent.
        **Campagne 30k (6 seeds) sur round_robin** : mean 62%→65% (+3), mais
        variance élevée — seed 123 : 76%→53% (−23), seed 1 : 23%→56% (+33),
        seed 5 : 81%→92% (+11), seed 99 : 27%→38% (+11), seed 7 : 84%→70%
        (−14), seed 42 : 82%→80% (−2). Ni victoire nette (novelty : aucun seed
        ne régresse) ni échec net (comme les réducteurs précédents) — premier
        cas mixte du projet.
        **Diagnostic demandé par Robin (seed 123, CSV tick-par-tick, défaut vs
        round_robin)** : les deux trajectoires sont **identiques bit à bit
        jusqu'à ce que la population atteigne `max_size=400`** (~tick 3400) —
        avant ça, rarement plus d'un agent éligible par tick, donc round-robin
        et le greedy legacy sont mathématiquement équivalents. Elles divergent
        exactement au moment où une vraie compétition multi-agents apparaît :
        round-robin change l'ORDRE des naissances → change l'ordre de
        consommation du RNG (mutations) → cascade chaotique. **Pas de bug** :
        même sensibilité aux effets fondateurs / à l'ordre de reproduction
        que tous les leviers précédents (crossover, fitness sharing, biais,
        critère minimal) — documentée depuis poc2.2. Round-robin ne fait que
        redistribuer la loterie des mutations précoces différemment par seed.
        Décision Robin : **ne pas promouvoir**, même profil de risque que les
        réducteurs à variance élevée déjà écartés. `default.yaml` garde
        `max_children_per_tick` et `reproduction_round_robin` absents (=0/false,
        legacy). Bonus livré au passage : `tools/campaign.py` affiche
        maintenant une ligne de progression périodique (`--progress-interval`,
        `--quiet`) — plain-text, pas de barre carriage-return, lisible en
        direct comme dans un log. 8 nouveaux tests, 202 verts, black clean,
        pylint 9.96/10. Détails : `docs/FALSIFIED-truncation.md`.
- [x] ✅ **K-sweep (`agent.apples_per_offspring`) — MEILLEUR RÉSULTAT NET DU
        PROJET, PROMU** (2026-07-15). Reprise du point ouvert poc2.2 ÉTAPE 10
        (« régler K »), motivée par le défaut post-densité qui n'est plus
        uniforme (seed 99 à 32 % @30k pendant que 42/5 tiennent 85-86 %).
        Sweep 15k/6 seeds K∈{1.5,2.0,2.5,3.0,3.5,4.0,5.0} : tendance nette,
        K bas > K haut, K=1.5 gagne (67 % vs 58 % défaut). **Confirmation
        30k** : moyenne **66→79 % (+13)**, **5/6 seeds montent (jusqu'à +24
        sur seed 99), le 6e quasi stable (7 : 77→76, −1)** — même profil
        qu'un levier additif (aucun effondrement) mais un gain net supérieur
        à novelty (+10) et densité (+4). L'effet s'AMPLIFIE de 15k à 30k
        (67→79), pas d'érosion. **`default.yaml` promu** :
        `agent.apples_per_offspring` 3.0→1.5, rien d'autre touché. 216 tests
        verts, black clean, pylint 10/10. Détails : `docs/RESULTS-k-sweep.md`.
- [x] ✅ **Modèle d'îles — FALSIFIÉ, réducteur net** (2026-07-15). Piste
        research-roadmap (alternative structurelle au crossover) :
        `population.num_islands` (défaut 1=legacy) partitionne la pop en N
        sous-populations quasi-isolées (slots/priorité/mating pool séparés),
        migration en anneau (`migration_interval_ticks`, `migration_count`).
        Campagne 6 seeds/30k vs le nouveau défaut (K=1.5) : moyenne
        **79%→68% (−11)**, **les 6 seeds régressent** (7 : 76→48, pire cas),
        profil réducteur classique (même famille que crossover/fitness
        sharing/biais/critère minimal). Diagnostic : 4 îles de 100 agents
        rouvrent la dérive fondatrice que poc2.2 avait corrigée en passant
        de pop 200→400 — chaque île isolée est fonctionnellement une petite
        population, en-deçà du régime robuste. `default.yaml` garde
        `num_islands` absent (=1). Mécanisme câblé + testé comme référence
        (14 tests dédiés). 216 tests verts, black clean, pylint 10/10.
        Détails : `docs/FALSIFIED-islands.md`.
- [x] ✅ **Instrumentation étendue (diagnostics) — densité, captures
        dirigées/fortuites, N_e, métriques déjà calculées** (2026-07-15,
        demande Robin). Observationnel pur — zéro risque sur la sim, aucune
        campagne de falsification requise. `src/diagnostics.py` (nouveau
        module) : `steer_score` migré de `tools/steer_probe.py` (tools/ ne
        doit pas être importé par src/), `classify_capture`/
        `capture_lookback_ticks` migrés de `tools/apple_capture_probe.py`
        avec son bug de calibration connu corrigé (fenêtre dérivée de
        `sensors.max_distance/agent.max_speed` au lieu d'un lookback fixe de
        30 ticks qui ne suivait pas `max_speed`), `local_agent_density`/
        `local_apple_density` (échantillonnées seulement aux captures, pas
        à chaque tick), `effective_population_size` (N_e, Crow & Kimura,
        fenêtre glissante `diagnostics.ne_window_ticks`, approximation
        documentée pour générations chevauchantes). CSV étendu de 13→26
        colonnes (steer_score/forager%/hidden/novelty moyens, densités
        globale+locale agents/pommes, %adjacent/directed/undirected,
        apples_eaten_per_tick, N_e). Nouveau `DiagnosticsConfig` (section
        optionnelle, tout par défaut = comportement legacy inchangé).
        `Agent.eat()` retourne désormais la liste des pommes mangées (au
        lieu du compte) pour permettre la classification ; `Agent` gagne
        `directed_captures`/`fortuitous_captures` (cumul lifetime, mirroring
        `apples_eaten`). 31 nouveaux tests (diagnostics + config + intégration
        simulation), 247 tests verts, black clean, pylint 10/10.
- [x] ✅ **Correctif critique — `tools/campaign.py` n'activait JAMAIS le CSV
        logger** (2026-07-15, trouvé en répondant à la question de Robin
        « mes métriques seront-elles observées dans les prochaines
        mesures ? »). Toutes les campagnes de recherche du projet (K-sweep,
        îles, novelty, densité, critère minimal, troncature…) tournent via
        `tools/campaign.py`, qui bouclait `sim.tick()` sans jamais appeler
        `open_csv_logger()` — ni les colonnes historiques ni les nouvelles
        n'étaient donc écrites, seul le tableau récapitulatif de fin de run
        l'était (calcul indépendant). Corrigé : `_run_seed` ouvre/ferme le
        logger comme `main.py`. Bug connexe trouvé et corrigé au passage :
        `Simulation._run_id` a une résolution à la SECONDE — des seeds
        lancés en parallèle par `ProcessPoolExecutor` (quasi simultanément)
        pouvaient partager le même `_run_id` et donc écrire CSV +
        best-genome JSON dans le MÊME dossier, s'écrasant mutuellement (bug
        préexistant, indépendant du CSV, présent depuis le début du projet).
        Fix : chaque seed reçoit désormais un sous-dossier dédié
        (`logs/.../seed<N>/<run_id>/`). **Vérifié bit-à-bit que l'activation
        du CSV ne change RIEN au déterminisme** (positions/énergies/record/
        repro identiques avec logger on/off, 5000 ticks) — les campagnes
        déjà documentées (K-sweep, îles, etc.) restent valides. 247 tests
        verts (inchangés, `tools/` non couvert par pytest), black clean,
        pylint 9.94/10 (idem avant, warnings préexistants hors périmètre).
- [x] ✅ **Audit profond du code (demandé par Robin) — 2 bugs réels corrigés,
        reste vérifié sain** (2026-07-15, `c25263b`). Lecture intégrale de
        `src/` + `tools/`, chaque hypothèse vérifiée empiriquement (pas juste
        raisonnée).
        **(1) FUITE MÉMOIRE confirmée** : `_log_row()` retournait tôt sans
        CSV ouvert, sautant `_diagnostics_row()` — seul endroit purgeant les
        accumulateurs. Toute boucle `tick()` sans `open_csv_logger()`
        (`tools/run_and_probe.py`, boucle d'éval, futur HyperNEAT) faisait
        croître sans borne `_birth_events` (qui épingle des Agent morts +
        génomes/réseaux) et les listes de densité. Prod non impactée (tous les
        chemins ouvrent le CSV) mais piège latent. Fix :
        `_reset_interval_accumulators()` + prune N_e appelés à chaque
        intervalle de log avec OU sans CSV.
        **(2) PERF / hitch** : `steer_score` recalculé sur toute la pop à
        chaque ligne de log (56 ms @pop 400 /100 ticks, réédition réduite du
        freeze corrigé). Or invariant pour un réseau gelé → mis en cache sur
        l'Agent (`Agent.steer_score`, lazy, mémoïsé) comme
        `behavior_descriptor`. Sweep 56 ms → ~0 en régime stationnaire.
        Déterminisme CSV on/off toujours bit-à-bit. 3 nouveaux tests, 249
        verts, black clean, pylint 9.96/10.
        **Vérifié NON problématique** : îles > max_size (testé, n'arrive pas —
        migration nette-nulle). **Mineurs relevés, non corrigés** (faible
        valeur, à faire dans une passe cleanup dédiée) : `run_and_probe.py`
        code en dur `0.1` au lieu de `diagnostics.forager_threshold` ;
        `Genome.from_json`/`from_dict` ne fait pas `bump_node_floor` (latent,
        aucun appelant ne mute un génome chargé) ; `Environment.in_safe_zone`
        + `Simulation.run()` quasi-morts (tests seulement) ;
        `apple_capture_probe.py` duplique `classify_capture` désormais dans
        `src/diagnostics.py` ; `steer_probe.py` `open()` sans context manager ;
        3 warnings pylint renderer préexistants (K_LEFT faux positif, etc.).