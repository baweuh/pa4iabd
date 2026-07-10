# Audit de tuyauterie fonctionnelle — poc2.3

> **Question posée** : « est-ce que tout ce qui est implémenté marche vraiment ?
> la tuyauterie est-elle pleinement connectée, fonctionnelle et *utilisée* ?
> Enquête principalement autour des agents. »
>
> **Date** : 2026-07-09 · **Branche** : poc2.3 · **Config auditée** : `config/default.yaml`
> **Méthode** : lecture exhaustive de `src/`, grep d'usage des symboles, run
> instrumentée pilotant `Simulation.tick()` directement (seed 42, 1250 ticks),
> `pytest` complet.

---

## 0. Verdict

**La boucle de vie de l'agent est pleinement connectée et fonctionne réellement.**
Mais « connecté » ≠ « utilisé » : une part notable du code est **présente, testée,
et jamais empruntée** par la config de référence. Ce sont des leviers
d'expérimentation désactivés (la plupart falsifiés dans les audits précédents),
pas des bugs. `148/148` tests passent.

---

## 1. Preuve d'exécution (seed 42, config par défaut)

Run instrumentée pilotant `tick()` directement (le CSV n'est pas flushé sur
SIGTERM, d'où l'instrumentation directe) :

| tick | pop | food restante | record pommes | reproductions | maxgen | meangen |
|-----:|----:|--------------:|--------------:|--------------:|-------:|--------:|
| 0    | 200 | 160           | 0             | 0             | 0      | 0.00    |
| 250  | 220 | 79            | 7             | 13            | 2      | 0.06    |
| 500  | 251 | 49            | 9             | 54            | 3      | 0.25    |
| 750  | 295 | 51            | 11            | 112           | 4      | 0.53    |
| 1000 | 343 | 23            | 15            | 169           | 4      | 0.74    |
| 1250 | 400 | 24            | 15            | 231           | 5      | 0.93    |

Lecture : la nourriture chute de 160→24 (les agents chassent vraiment), le record
grimpe, la population atteint sa capacité (`max_size=400`), les lignées
s'approfondissent (`maxgen=5`). La chaîne complète
`sense (16 raycasts) → network.activate → sorties égocentriques → move → eat →
metabolize → is_dead → reproduce → CSV → dump meilleur génome → injection élite`
tourne de bout en bout.

---

## 2. 🟢 Actif et vérifié

- **Boucle de perception→action** : `Agent.sense` → `NeuralNetwork.activate` →
  sorties égocentriques (`output[0]×max_speed`, `output[1]×max_turn_rate`) →
  `move` → `eat` → `metabolize`. Vérifié par la déplétion de nourriture.
- **Reproduction couplée au foraging** (`apples_per_offspring: 3.0`) : chemin
  `Simulation._reproduce_by_foraging`. C'est lui qui pilote les 231 naissances.
  Fécondité ∝ pommes cumulées ⇒ vraie pression de sélection.
- **Cycle de vie** : `is_dead` (famine ou `max_age`), recomposition de population,
  cap à `max_size`.
- **Observabilité** : CSV (13 colonnes), `count_species` + `mean_pairwise_distance`
  alimentent bien le fichier, dump du meilleur génome + injection d'élite
  (`_inject_elite`).

---

## 3. 🟡 Câblé, testé, mais **dormant** dans la config par défaut

Code jamais exécuté au runtime avec `default.yaml`. C'est le cœur de la réponse :
beaucoup de machinerie existe et est couverte par les tests, mais `default.yaml`
ne l'emprunte jamais.

| # | Élément | Pourquoi dormant | Conséquence concrète |
|---|---------|------------------|----------------------|
| 1 | `_reproduce_by_energy()`, `Agent.can_reproduce()`, `agent.reproduction_threshold` | `apples_per_offspring > 0` bascule sur le chemin foraging | Le seuil de repro (1.1) n'a **aucun effet** |
| 2 | Crossover : `Genome.crossover`, `_align_genes`, `_inherit`, `Simulation._pick_mate` | `crossover_rate: 0.0` ⇒ `_pick_mate` renvoie toujours `None` | Toute la repro sexuée NEAT est morte (crossover falsifié, cf. AUDIT-poc2.3 volet 3-4) |
| 3 | `speciation.compatibility_distance` **côté sélection** | Crossover off ⇒ jamais appelé pour le choix de partenaire | Ne sert **que** au logging ; n'influence aucune décision d'agent |
| 4 | Capteurs riches : branche `split_distance` de `sense`, ajout `proprioception`, `apples_in_view` | 3 toggles OFF (layout 49) | Voir #5 |
| 5 | `Agent._last_actual_speed` (calculé dans `move()`) | `proprioception` OFF ⇒ `sense()` ne le lit jamais | **Calcul mort à chaque tick** |
| 6 | Terme d'activité `move_cost × _last_speed` dans `metabolize()` | `move_cost: 0.0` | Toujours nul ; `_last_speed` calculé puis multiplié par 0 |
| 7 | Chemin sparse du génome fondateur : `Genome._founder_inputs_for` (`rng.sample`) | `initial_connectivity: 1.0` | Toujours repassé par le fully-connected (sparse falsifié, cf. commit 442256f) |

Aucun n'est un bug : ce sont des interrupteurs d'ablation. Mais si on veut un code
« qui n'expose que ce qui sert », il y a matière à élaguer ou à documenter comme
explicitement expérimental.

---

## 4. 🔴 Réellement inutilisé (au-delà de la config)

- **`Environment.in_safe_zone()`** : appelé uniquement dans les tests. Le code de
  prod utilise `Simulation._safe_spawn_position()` qui recalcule les bornes
  indépendamment. Vrai code mort fonctionnel (bénin).

*(Note : `agent.end_of_life_ticks` n'est utilisé que par `renderer.py` pour le
colorisation de fin de vie — ce n'est pas du code mort, juste un paramètre
purement visuel, cohérent avec l'invariant n°7.)*

---

## 5. ⚠️ Performance — le vrai point faible

Le raycast est **O(population × rayons × pommes)** sans index spatial : à capacité
(400 agents × 16 rayons × 160 pommes ≈ 1 M tests ray-cercle/tick). Mesuré :
**~15–25 ticks/s**. Une run documentée de 15k–30k ticks prend donc **15–30 min**.
Fonctionnel, mais c'est le goulot qui a fait timeout les premières tentatives
d'exécution. Piste d'optimisation évidente : index spatial (grille/quadtree) sur
les pommes, ou vectorisation NumPy des raycasts.

---

## 6. Note sur la qualité de la sélection

`meanforage` reste plat (~0.003) sur 1250 ticks — mais avec `maxgen=5` c'est trop
tôt pour conclure, et ça colle au fil rouge documenté du projet (*fourrage réel
mais faiblement sélectionné*, cf. SYNTHESE.md §1). Ce n'est pas un bug, c'est le
comportement attendu du modèle. Un audit de sélection sur une run longue
(15k+ ticks) reste ouvert.

---

## 7. Recommandations (ouvertes, non appliquées)

1. **Élaguer / marquer explicitement** le code dormant du §3 (soit le supprimer,
   soit le regrouper derrière des toggles clairement documentés « expérimental »).
2. **Optimiser le raycast** (index spatial sur les pommes) — débloque les runs
   longues nécessaires pour juger la sélection.
3. **Auditer la sélection** sur ≥15k ticks une fois la perf réglée.
4. Aligné avec la feuille de route mémoire : le **fitness sharing NEAT** n'est
   toujours pas implémenté (les métriques de speciation existent, la boucle de
   sélection ne les utilise pas).
