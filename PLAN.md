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
- [x] ✅ **Cleanup mineur post-audit** (2026-07-15, `234fc6e`) : les 5
        points relevés à l'audit ci-dessus traités — seuil forager en dur
        (`run_and_probe.py`) remplacé par `diagnostics.forager_threshold`,
        `steer_score(...)` remplacé par la propriété cachée `a.steer_score` ;
        monkeypatch `Environment.tick_respawns` (devenu redondant,
        `Apple.spawn_tick` tracké nativement) supprimé de
        `apple_capture_probe.py`, classification réutilisée depuis
        `src.diagnostics` ; `steer_probe.py` `open()` avec context manager ;
        3 warnings pylint `renderer.py` corrigés (10.00/10). 249 tests
        verts, black clean, pylint propre.

## Branche poc2.5 — HyperNEAT (encodage indirect, MVP) ✅ FALSIFIÉ (V1+V2+V3+V4), chantier clos
> POC hors numérotation. Recherche n°4 (dernier point ouvert de la feuille de
> route, voir memory `research-roadmap`) : au lieu que le génome décrive
> directement le réseau, il décrit un CPPN interrogé sur la géométrie du
> capteur pour produire les poids d'un substrat fixe. Convenu avec Robin
> (2026-07-15) : MVP dé-risqué avant la version complète. **Verdict V1 :
> pire régression du projet (moy 67%→15%), root cause diagnostiquée
> (substrat dense + CPPN sans nœud caché sature et noie le signal).**
> **V3 (2026-07-16, bootstrap d'1 nœud caché CPPN à la genèse) referme
> l'essentiel de l'écart à 30k (moy 19%→68%, vs 79% défaut) mais reste
> falsifié au sens strict : un seed s'effondre (123 : 82%→12%).** **V4
> (2 nœuds bootstrappés) régresse nettement (68%→39%) : la relation n'est
> PAS monotone, N=1 est un point de fonctionnement, pas un curseur — chantier
> clos sur ce constat, meilleur résultat = V3, non promu.** Détails
> complets : `docs/DESIGN-hyperneat-mvp.md`, `docs/FALSIFIED-hyperneat.md`.
- [x] **Session 1 — mécanique + outil d'itération rapide** : `src/geometry.py`
        (extrait de `agent.py`, casse un cycle d'import) ; `src/hyperneat.py`
        (coordonnées substrat génériques à tout `SensorConfig`, CPPN 6→1,
        construction du substrat dense) ; `HyperNEATConfig` (section
        optionnelle, `enabled: false` par défaut — zéro impact sur le
        comportement existant) ; câblage conditionnel dans
        `Simulation._spawn_agent`/`Agent.__init__` ; `NeuralNetwork.activate()`
        généralisé à N sorties (rétrocompatible, nécessaire pour le CPPN à 1
        sortie) ; `config/lever_hyperneat_mvp.yaml` ; `tools/inspect_network.py`
        (steer_score + descripteur + score de régularité géométrique vs
        témoin aléatoire + test de transfert de résolution, 0 tick). Sanity
        check sur un génome réel : substrat ~3× plus lisse qu'un génome
        direct aléatoire, steer_score stable en doublant la résolution sans
        ré-évoluer — le mécanisme produit ce qui était visé. 267 tests
        verts, black clean, pylint 9.98/10.
- [x] **Session 2 — `tools/trace_lineage.py`** : reconstruit la vraie lignée
        du champion final (agent→parent→…→fondateur) sur un run RÉEL,
        pop-pleine (monkeypatch process-local de `Agent.reproduce`, jamais
        `src/`, même technique que `apple_capture_probe.py`). Champion
        choisi par `steer_score` (pas `apples_eaten`, qui confond
        compétence et longévité). Coût borné à ce seul run (génomes
        légers, jamais l'`Agent` complet). Logique de reconstruction
        vérifiée indépendamment sur un run réel (6 générations, chaîne
        cohérente). 267 tests verts (inchangé, `tools/` non couvert par
        pytest), black clean, pylint 9.97/10.
- [x] ✅ **Campagne 6 seeds de falsification — FALSIFIÉ, pire régression
        du projet** (42,7,123,1,5,99, 15k ticks,
        `config/lever_hyperneat_mvp.yaml` vs `default.yaml` fraîchement
        relancé). Moy foragers **67%→15% (−52)** — dépasse la pire
        régression précédente (biais NEAT, −34). **Les 6 seeds
        régressent**, `steer_median` passe négatif sur presque tous les
        seeds, 2 seeds s'effondrent démographiquement (123: 190/400,
        5: 43/400 — jamais observé sur aucun levier précédent). Root
        cause diagnostiquée (pas juste un score) : substrat dense +
        CPPN sans nœud caché à la genèse (6 poids seulement, fortement
        corrélés) sature le `tanh` de sortie et noie le signal d'un
        rayon isolé — vérifié empiriquement (`steer_score` exactement
        0,0 sur 74/100 CPPN fondateurs vs 0/100 génomes directs).
        `hyperneat.enabled` reste absent (=false) dans `default.yaml`.
        Détails complets : `docs/FALSIFIED-hyperneat.md`.
- [x] ✅ **HyperNEAT V2 — correction ciblée, RE-FALSIFIÉ (amélioration
        réelle mais insuffisante)**. Diagnostic affiné avant campagne
        (sweep founder-level, 0 tick) : la sparsification seule
        (`hyperneat.connectivity`, câblée + testée comme mécanisme
        secondaire, 4 tests dédiés) réduit mais n'élimine pas la
        dégénérescence. Vraie cause dominante : `weight_scale=3.0` sature
        le CPPN (0 nœud caché = purement linéaire) AVANT même la sommation
        du substrat — fondateurs dégénérés 106/150 à scale 3,0 → 0/150 dès
        scale≤0,75. `config/lever_hyperneat_v2.yaml` : `weight_scale`
        3,0→0,5 (une seule variable, `connectivity` reste dense).
        **Campagne 6 seeds/15k : moy foragers 15%→19% (+4), toujours −48
        vs défaut (67%)**. Toujours falsifié — mais plus aucun effondrement
        démographique (V1 avait 2 seeds proches de l'extinction, tous à
        pop=400 en V2). `hidden` moyen reste quasi nul (0,05–0,17) :
        hypothèse retenue = évolvabilité du CPPN à 6 poids fortement
        couplés (pas juste la saturation fondatrice, déjà corrigée). V3
        (bootstrap nœuds cachés, mutation CPPN dédiée) **à décider avec
        Robin**, pas engagé. 273 tests verts, black clean, pylint 9.97/10.
        Détails complets (V1+V2) : `docs/FALSIFIED-hyperneat.md`.
- [x] ✅ **HyperNEAT V3 — bootstrap de nœud(s) caché(s) CPPN à la genèse,
        écart réduit mais RE-FALSIFIÉ (mixte)** (2026-07-16, décidé avec
        Robin : direction "bootstrap" retenue plutôt que "mutation CPPN
        dédiée", campagne lancée directement à 30k — précédent du levier
        densité, négatif à 15k/positif à 30k). Mécanisme :
        `hyperneat.bootstrap_hidden_nodes` (0=legacy) appelle
        `Genome.add_node` N fois sur le CPPN fondateur juste après
        `new_fully_connected`, dans `Simulation._spawn_agent` — réutilise
        l'opérateur de split NEAT déjà existant, aucune machinerie
        nouvelle. Sweep fondateur (0 tick) confirme qu'aucune
        dégénérescence n'est réintroduite. `config/lever_hyperneat_v3.yaml`
        = V2 (`weight_scale 0.5`) + `bootstrap_hidden_nodes` 0→1.
        **Campagne 6 seeds/30k (défaut aussi relancé frais à 30k pour
        comparaison directe) : moy foragers 79%(défaut)→68%(V3), −11** —
        écart réduit d'un facteur ~4-5 par rapport à V2 (−48) et V1 (−60).
        `hidden` moyen passe de 0,05–0,17 (V1/V2) à 0,87–1,40 : le CPPN
        complexifie enfin structurellement. **2/6 seeds dépassent le
        défaut** (1 : 68→92, +24 ; 99 : 56→91, +35 — 1ʳᵉ fois qu'un levier
        HyperNEAT bat le défaut, et nettement) ; 2 quasi stables (42, 7) ;
        **2 régressent lourdement, dont un effondrement** (5 : 96→50,
        −46 ; 123 : 82→12, −70, `steer_median` retombe à 0,000). Toujours
        falsifié au sens strict (pas de campagne 6/6 stable) — mais
        progrès net et diagnostiqué, pas un plateau. V4 (plus de nœuds
        bootstrappés, mutation CPPN dédiée, diagnostic ciblé du cas 123)
        **à décider avec Robin**, pas engagé automatiquement. 278 tests
        verts, black clean, pylint 9.99/10. Détails complets :
        `docs/FALSIFIED-hyperneat.md`.
- [x] ✅ **HyperNEAT V4 — 2 nœuds cachés bootstrappés, RELATION NON
        MONOTONE, régresse fort — chantier clos** (2026-07-16, décidé avec
        Robin : « on pousse » → teste si le lever V3 est un curseur qui
        continue d'aider en montant, `hyperneat.bootstrap_hidden_nodes`
        1→2, `config/lever_hyperneat_v4.yaml`). Sweep fondateur (0 tick,
        bootstrap 1/2/3) confirme à nouveau qu'aucune valeur ne dégénère
        statiquement — question invisible à 0 tick, campagne lancée
        directement à 30k comme V3. **Campagne 6 seeds/30k : moy foragers
        68%(V3)→39%(V4), −29** — contredit l'hypothèse "plus de nœuds =
        mieux". `hidden` moyen monte comme prévu (0,87–1,40→2,03–2,73, le
        bootstrap fonctionne mécaniquement) mais la compétence NE suit
        PAS : les 2 seeds qui battaient le défaut en V3 s'effondrent (1 :
        92→32, −60 ; 99 : 91→14, −77, pire chute de la campagne), seed 42
        stable en V3 chute aussi (97→28, −69), `steer_median` repasse
        négatif sur 4/6 seeds (symptôme V1). Seule amélioration : 123
        (le pire cas V3) remonte un peu (12→33) sans devenir bon.
        Diagnostic : un 2ᵉ nœud caché double la profondeur/dimension du
        CPPN sans que le régime de mutation (`add_node_rate`,
        `weight_mutation_rate`) soit ajusté pour cette complexité accrue —
        même dynamique que le génome sparse poc2.3/le nœud de biais
        poc2.4 (ajouter de la complexité fondatrice sans adapter le
        régime évolutif qui doit l'exploiter dégrade). **Chantier
        HyperNEAT clos** : meilleur résultat = V3 (`config/
        lever_hyperneat_v3.yaml`), toujours falsifié au sens strict, non
        promu ; `hyperneat.enabled` reste absent (=false) dans
        `default.yaml`. Détails complets : `docs/FALSIFIED-hyperneat.md`.
## Branche poc2.6 — todo grossière, à affiner avec Robin 🔄
> Ouverte depuis `poc2.5` (2026-07-16) après clôture du chantier HyperNEAT
> (V1→V4, falsifié) et feuille de route recherche 5/5. Constat de Robin :
> la plupart des leviers testés jusqu'ici (fitness sharing, troncature,
> crossover, génome sparse, critère minimal, îles, archive, biais,
> HyperNEAT) reposent tous sur la **sélection/reproduction**. Cette liste
> couvre 3 candidats — un seul a un diagnostic préalable (V5), les deux
> autres sont volontairement grossiers, **à transformer en hypothèse
> précise avant d'engager toute campagne** (discipline du projet : jamais
> de campagne sans diagnostic). Ordre et scope à trancher avec Robin.

- [ ] **Multivers solo — 1 agent par cellule physiquement isolée
        (proposition Robin, 2026-07-16, design fait, rien engagé).**
        Question plus tranchée que la campagne d'échelle poc3 en cours :
        isoler l'espace physique (qui rencontre qui, qui mange quoi) en
        gardant la sélection/reproduction/novelty GLOBALES sur tous les
        univers — teste si l'échelle aide par la taille de l'échantillon
        évalué seule, ou si l'interaction multi-agents (compétition) est
        elle-même nécessaire. Diffère explicitement du modèle d'îles
        (falsifié, poc2.4) : les îles fragmentaient la sélection
        elle-même (rouvrait la dérive fondatrice) — ici seule la
        physique est fragmentée, la sélection reste sur la population
        entière. Nécessite un vrai changement de code (pas juste un
        fichier de config) : zone safe par cellule (`Environment`), murs
        internes + perception de mur par cellule (`agent.py`, clamp +
        raycast), mapping stable slot↔cellule pour le respawn
        (`Simulation._spawn_agent`). Détails complets, options
        considérées (sharding spatial recommandé vs multivers
        process-level écarté), risques à vérifier avant campagne :
        `docs/DESIGN-multiverse-solo.md`.
- [ ] **HyperNEAT V5 — régime de mutation CPPN dédié.** Seule piste avec
        un diagnostic déjà établi (V2/V3, `docs/FALSIFIED-hyperneat.md`) :
        le CPPN fondateur progresse à peine structurellement (`hidden`
        quasi nul ou lentement croissant) avec le régime de mutation
        hérité de l'encodage direct (`add_node_rate` 0,03/tick,
        `weight_mutation_rate` 0,15) — jamais ajusté pour un génome à 6-14
        poids fortement couplés. Bien scopée, coût connu (~30 min/itération,
        sweep 0 tick + campagne 6 seeds/30k).
- [ ] **Repro non canonique — à transformer en hypothèse avant campagne.**
        Deux écarts à la littérature repérés en audit (memory
        `research-roadmap`), jamais testés comme leviers : `Genome.
        crossover` traite toujours `self` comme parent "fitter" sans
        comparer les fitness ; la reproduction ne comble que les slots
        vidés par la mort (pas de turnover forcé façon rtNEAT). Risque
        élevé de falsification supplémentaire — quasi tous les leviers de
        sélection/reproduction du projet ont échoué (troncature, critère
        minimal, îles, crossover lui-même) — donc priorité basse tant
        qu'aucun diagnostic ne motive l'un ou l'autre spécifiquement.
- [ ] **Pistes hors sélection/reproduction — recherche littérature
        2026-07-16, aucun diagnostic encore, à affiner :**
    - **Plasticité Hebbienne/neuromodulée pendant la vie de l'agent**
        (Stanley, Bryant & Miikkulainen 2003 — NEAT + règles Hebbiennes
        évoluées, testé sur un domaine de **foraging** conçu pour exiger
        un changement de politique en cours de vie ; Soltoggio et al.
        2018 « Born to Learn », survey EPANN). Catégorie fondamentalement
        différente de tout ce qui a été tenté (adaptation individuelle
        pendant la vie, pas seulement inter-générationnelle) ; nécessite
        juste une règle de mise à jour de poids en NumPy pur, pas de
        framework ML (respecte `CLAUDE.md`). Le lien le plus direct avec
        la tâche de foraging du projet parmi toutes les pistes trouvées.
    - **Quality-Diversity — MAP-Elites / Novelty Search with Local
        Competition** (Lehman & Stanley 2011 ; Mouret & Clune 2015).
        Remplace la sélection générationnelle par un archive de niches
        comportementales retenant l'élite par niche. NSLC en particulier
        combine directement novelty (déjà promu en défaut) avec une
        compétition **locale** plutôt que globale — differe de l'archive
        de nouveauté déjà falsifiée (mécanisme d'archive différent, pas
        juste un stockage passif de comportements obsolètes).
    - **ALPS — Age-Layered Population Structure** (Hornby 2006).
        Alternative aux îles (déjà falsifiées, poc2.4) pour préserver la
        diversité : couches d'âge protégeant les jeunes génotypes de la
        compétition directe avec les anciens, plutôt qu'une isolation
        géographique. Mécanisme différent pour un objectif similaire
        (limiter la convergence prématurée) déjà tenté et raté une fois.
    - **Mutation auto-adaptative** (façon evolution strategies — le taux
        de mutation évolue lui-même par génome au lieu d'être une
        constante YAML globale). Tension à trancher avec l'invariant n°1
        (zéro valeur hardcodée, tout vient de `SimConfig`) : le taux
        s'auto-règle par l'évolution, pas hardcodé, mais change la nature
        du paramètre (plus une constante lue en config, un état évolué).

**Sur les leviers "ML"** : le projet interdit tout framework ML
(`neat-python`/torch/tensorflow/gym, cf. `CLAUDE.md`). Parmi les pistes
ci-dessus, la plasticité Hebbienne et la mutation auto-adaptative sont
les deux qui restent dans ces clous (règles de mise à jour codées à la
main, NumPy pur) tout en apportant une mécanique réellement différente de
l'évolution pure ; un RL classique (Q-learning/policy gradient) sortirait
du cadre du projet (boucle d'entraînement séparée, tension avec le
principe "réseau feedforward + évolution seule") et n'est pas retenu ici.

## Branche poc3 — Topologie de réseau fixe + forward pass batché ✅ archi livrée, CLOSE sans verdict d'échelle
> Ouverte depuis `poc2.6` (2026-07-16) après recherche littérature (Hamon
> et al. 2023, Bejjani et al. 2025 : dans le même paradigme non-épisodique/
> sélection implicite que ce projet, l'émergence de comportements complexes
> est liée à l'**échelle**, pas au mécanisme de sélection — cohérent avec
> l'historique du projet, où seuls les leviers d'échelle/écologie ont
> marché). Verrou identifié (audit poc2.4) : le forward pass NEAT
> hétérogène est un plafond dur, non batchable ; la population par défaut a
> <0,5 nœud caché en moyenne après 30k ticks — NEAT paie son coût plein
> pour une évolution de topologie qui n'a quasiment jamais lieu. Détails
> complets : `docs/DESIGN-poc3-fixed-topology.md`.

- [x] **Génome à topologie fixe** (`src/genome.py` réécrit) : `Genome`
        devient un vecteur de poids plat + `layer_shapes` (dérivé de
        `NetworkConfig.hidden_size`, jamais hardcodé). Plus de mutation
        structurelle (add_node/add_connection/remove_*/InnovationTracker
        supprimés) — feedforward garanti par construction, plus de DFS
        anti-cycle. `hidden_size: 0` (v1) = couche linéaire 49→2, même
        capacité effective que le NEAT direct moyennait déjà.
- [x] **`src.network.batch_activate`** : forward pass de toute la
        population en un seul appel NumPy batché (`einsum` par couche),
        remplace la boucle `agent.decide()` par agent dans
        `Simulation.tick()`. Équivalence numérique verrouillée par test
        dédié (tolérance 1e-10, linéaire ET avec couche cachée).
- [x] **`src.speciation` simplifié** : distance = moyenne de différence
        absolue sur le vecteur de poids partagé (plus de concept
        excess/disjoint, qui n'avait de sens que pour des topologies
        variables). `assign_species`/`fitness_sharing` gardent la même
        signature d'appel.
- [x] **HyperNEAT supprimé** (décision explicite Robin — bâti sur l'API
        NEAT structurelle, déjà falsifié V1-V4, jamais promu) :
        `src/hyperneat.py`, `tools/inspect_network.py`,
        `tools/trace_lineage.py`, `tests/test_hyperneat.py`,
        `config/lever_hyperneat_{mvp,v2,v3,v4}.yaml`. Historique complet
        préservé sur `poc2.5`/`poc2.6`.
- [x] **Reste de l'écosystème réutilisé tel quel** : environnement,
        énergie, reproduction, capteurs, boucle de tick, renderer (panneau
        réseau adapté à la nouvelle forme, pas redessiné), novelty,
        K-sweep, densité.
- [x] ✅ **Vérification** : 238 tests verts (test_genome.py/test_network.py/
        test_speciation.py réécrits, test_hyperneat.py supprimé), black
        clean, pylint 9.99/10. Run réel headless sans crash, population
        stable à 400/400. **Perf (pop=400, 3000 ticks, comparaison directe
        poc2.6 vs poc3) : 56,2→72,1 ticks/s (×1,28)** — diagnostiqué par
        profil : `batch_activate` ne représente plus que 2,8 % du tick
        (contre 45 % "plafond dur" pour le forward pass NEAT hétérogène) —
        **le verrou visé est bien éliminé** ; le nouveau goulot dominant
        est `agent.eat()` (29 %, jamais batché) et `batch_sense` (49 %,
        déjà optimisé poc2.4), tous deux hors scope de ce chantier. Sanity
        comportementale (2 seeds/5000 ticks) : fourrage émerge normalement
        (73 %/33 %), rien de cassé.
- [ ] **Hors scope, sessions futures** : monter la population au-delà de
        400 (l'hypothèse même que ce chantier prépare), sweep
        `hidden_size` > 0, GPU/JAX, re-validation des leviers existants à
        plus grande échelle, nettoyage des ~37 configs legacy
        poc2.2-poc2.4 (structurellement incompatibles, seuls les 3
        utilisés par la suite de tests ont été corrigés), perf de
        `agent.eat()`/`batch_sense` (nouveau plafond identifié).

### Addendum poc3 — déblocage de l'échelle (même session)
- [x] **`src.agent.batch_eat`** : vectorise la consommation de pommes
        (NumPy, matrice agents×pommes), équivalence exacte avec la boucle
        séquentielle verrouillée par 5 tests dédiés
        (`tests/test_batch_eat.py`). `eat()` passe de 29 % à ~négligeable
        du tick.
- [x] **`novelty.max_pool_size`** : borne le coût O(pop²) de
        `population_novelty` (sous-échantillon partagé au-delà de la
        taille configurée, déterministe). 0 = illimité/exact (défaut,
        inchangé). 6 tests dédiés (`tests/test_novelty.py`), dont
        exclusion de soi garantie même échantillonné.
- [x] ✅ **Perf mesurée** (`novelty.max_pool_size: 300`) : 400→106,0 ;
        2000→32,8 ; 4000→19,3 ; 8000→12,3 ; 16000→6,7 ticks/s. Sans le
        correctif (novelty exacte), 8000 tournait à 2,8 ticks/s — lent
        (~3h/seed pour 30k ticks) mais PAS un crash mémoire, contrairement
        à ce que ce document affirmait initialement (corrigé après
        vérification). 16000 en exact non testé jusqu'à pop pleine (le
        tenseur (pop,pop,D) atteindrait ~32 Go, > les 15 Go de cette
        machine — plausible mais pas confirmé). Profil à 8000 :
        `batch_sense` redevient le coût dominant (37,5 %, linéaire,
        attendu), `population_novelty` tombe à 10,8 %. 249 tests verts,
        black clean, pylint 9.99/10. Détails :
        `docs/DESIGN-poc3-fixed-topology.md` (addendum).
- [x] ✅ **Campagne d'échelle round 1 (pop 400→4000) — RÉGRESSE, mais
        résultat CONFONDU, non concluant** (2026-07-16,
        `config/lever_scale_4000.yaml`, 6 seeds/30k,
        `logs/campaign_runs/scale4000_20260716_200310.log`). Une seule
        variable vs `default.yaml` : `population.max_size` 400→4000
        (`initial_size` 200→2000, même ratio). **Moyenne foragers 38 %**
        (42:54, 123:49, 5:38, 7:31, 99:30, 1:27), `steer_median` négatif
        sur **4/6** seeds. **Deux réserves majeures interdisent d'en
        conclure quoi que ce soit sur l'hypothèse d'échelle** :
        (a) **confound nourriture** : 4000 agents pour 160 pommes
            inchangées = compétition ~5× plus dense que le défaut — la
            régression peut venir de « pas assez à manger par tête »,
            pas de l'échelle elle-même ;
        (b) **la population n'a jamais dépassé `initial_size`** (les 6
            seeds finissent 1943–2010 sur un cap de 4000) : le régime
            visé n'a tout simplement jamais été atteint, cohérent avec
            une croissance bridée par la famine.
        **Aucun delta fiable ne peut être annoncé, seulement la valeur
        absolue mesurée** : il n'existe pas de campagne de référence
        poc3 à 30k dans `logs/campaign_runs/`. Le « 72 % » cité comme
        baseline dans `docs/DESIGN-multiverse-solo.md` n'est adossé à
        aucun log de ce dépôt ; le 79 % historique est un chiffre
        poc2.4, mesuré sous l'ancienne architecture NEAT, donc non
        comparable directement à une run poc3.
- [ ] ⛔ **Campagne d'échelle round 2 (pommes ×10, ratio pommes/agent
        restauré) — LANCÉE PUIS ABANDONNÉE, aucun verdict** (2026-07-16,
        `config/lever_scale_4000_scaled_food.yaml`,
        `logs/campaign_runs/scale4000_scaled_food_20260716_214445.log`).
        Devait lever le confound (a) du round 1 : `apple.count` 160→1600,
        même ratio que `max_size` 400→4000, de sorte qu'une régression ne
        puisse plus être imputée au manque de nourriture. **Interrompue à
        ~4 % (1200/30000 ticks)**, aucun process actif depuis. Le
        confound du round 1 reste donc entier.

### Clôture de la branche poc3 (2026-07-20, décision Robin)
Branche **close sans verdict** sur l'hypothèse d'échelle qui l'a motivée.
Le travail d'architecture livré ci-dessus (topologie fixe, forward pass
batché, `batch_eat`, `novelty.max_pool_size`) est réel, testé et mesuré —
il reste ici comme checkpoint réutilisable. Le backlog de recherche
repart de **poc2.6**, parce que ses candidats sont majoritairement liés à
l'architecture NEAT que poc3 a justement retirée :
- **HyperNEAT V5** dépend de l'API structurelle NEAT (CPPN → substrat),
  supprimée en poc3 (`src/hyperneat.py` et son outillage effacés) — ne
  peut vivre que sur l'archi poc2.5/poc2.6.
- **Repro non canonique**, volet « `Genome.crossover` traite toujours
  `self` comme le parent fitter sans comparer les fitness » : c'est un
  défaut d'alignement propre à NEAT (gènes excess/disjoint hérités du
  parent réputé fitter). Le `Genome.crossover` de poc3 est un tirage
  élément-par-élément 50/50 sur un vecteur de poids plat, où l'argument
  `fitter` n'a plus aucun effet — le point n'existe plus sous cette
  forme.
- Seules les pistes **indépendantes de la représentation** (plasticité
  Hebbienne, MAP-Elites/NSLC, ALPS, mutation auto-adaptative)
  s'appliqueraient indifféremment aux deux architectures.
