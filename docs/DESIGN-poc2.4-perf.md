# poc2.4 — Optimisation du débit de simulation (design + prototypes chiffrés)

> Objectif : fluidifier la **boucle de recherche** (campagnes multi-seeds), pas
> un run isolé. Deux leviers indépendants et **composables**, chiffrés sur le
> code réel de cette branche. Aucun n'abandonne NEAT (contrainte du projet :
> réseaux à topologie hétérogène, aucun framework ML).

## Baseline mesurée (cette machine, `config/default.yaml`, seed 42)

- **58,4 ticks/s** (pop 200→400, 3000 ticks).
- Un run 30k ticks ≈ **8,6 min/seed** → campagne 3 seeds séquentielle ≈ **26 min**.

Profil d'un tick (cProfile, 800 ticks) — part cumulée :

| Étape | % du tick | Nature |
|---|---:|---|
| `sense()` / raycast | **57 %** | NumPy **par agent** (`_ray_circles_vec` 27 %, `_ray_walls_vec` 15 %) |
| `network.activate()` (forward) | **23 %** | boucle Python sur dict, topologie **hétérogène** par agent |
| `eat()` | **12 %** | `math.hypot` en boucle Python (11 M appels/800 ticks) |
| reste (move, métabolisme, repro) | **8 %** | objets Python |

Tout est une boucle `for agent in self.population` (195 k appels `activate`/800 ticks).
Le raycast est déjà vectorisé **par agent** — mais payé une fois par agent.

---

## Levier 1 — Campagnes multi-seeds en parallèle  ✅ prototypé + livré

### Design
Chaque seed est une `Simulation` **totalement indépendante** (`Random(seed)`,
aucun état partagé). On les répartit sur un `ProcessPoolExecutor`
(`max_workers = min(#seeds, cœurs-1)`). Zéro ligne de la simulation ne change :
c'est de l'orchestration pure au-dessus de `run_and_probe`.

Livré comme `tools/campaign.py` — même table de verdict que `run_and_probe`
(steer médian, % fourrageurs r>0,1, nœuds cachés) agrégée sur les seeds.

```
python -m tools.campaign config/default.yaml 30000            # trio 42,7,123
python -m tools.campaign config/lever_x.yaml 30000 42,7,123,5 --workers 4
```

### Chiffres mesurés
Campagne 3 seeds × 1500 ticks : **séquentiel 76,0 s → parallèle 28,8 s = ×2,64**,
résultats **bit-identiques** (mêmes pop/tick counts — déterminisme préservé).
Le facteur monte avec le nombre de seeds jusqu'à la limite cœurs (12 dispo).

### Risques / limites
- **Nul côté sémantique** : la simulation n'est pas touchée.
- Mémoire : chaque process charge son propre NumPy + population ; négligeable à pop 400.
- Overhead de spawn : ~amorti sur un run 30k ticks (invisible).
- **Point d'attention CSV** : si les seeds écrivent des CSV, les `run_id` basés
  sur l'horodatage peuvent collisionner au démarrage simultané. `tools/campaign.py`
  n'ouvre **pas** de CSV (il ne collecte que les métriques finales) → non concerné.
  Si on veut les CSV en parallèle, préfixer le `run_dir` par le seed.

### Statut : **implémenté**, prêt à l'emploi. ROI immédiat, risque nul.

---

## Levier 2 — Tick vectorisé sur la population  ✅ implémenté + validé

### Le verrou sémantique actuel
Aujourd'hui l'étape 1 du tick (`simulation.py:154`) entrelace perception ET
capture dans **une seule boucle** : l'agent N perçoit un monde déjà modifié par
les agents < N (pommes qu'ils viennent de manger ce tick). C'est pour ça que le
batch pop-entière avait été écarté ([[numpy-raycast-todo]]).

### Design retenu — « geler puis percevoir en batch » (delta sémantique minimal)
On **fige le monde au début du tick**, on perçoit toute la population en **une
passe NumPy** contre ce snapshot, puis on garde la capture **séquentielle** en
ordre d'index (inchangée) :

| Phase | Contenu | Vectorisé ? |
|---|---|---|
| A · Percevoir | raycast batché `(P × rayons × pommes)` en un broadcast → matrice `(P, num_inputs)` | **oui** (le gain) |
| B · Décider | forward pass | non — reste par agent (topologies NEAT hétérogènes) |
| C · Agir | `move()` égocentrique (élémentaire) | vectorisable (phase 2) |
| D · Manger + métaboliser | capture séquentielle index-ordre, **identique à aujourd'hui** | non |

**Seul changement de comportement** : un agent peut désormais *percevoir* une
pomme qu'un agent d'index inférieur mange le même tick (avant, il ne la voyait
déjà plus). C'est un delta minime — et sans doute **plus correct** (simultanéité
au sein d'un tick), il supprime un artefact d'ordre de liste. La résolution de
la capture, elle, ne change pas → pas de problème de double-mange.

### Chiffres mesurés
**Perception isolée** (spike `spike_batch_perception.py`, pop 400, 16 rayons) :
équivalence **bit-à-bit** avec `sense()`, **15,2 ms → 1,6 ms = ×9,8**.

**End-to-end après implémentation** (`config/default.yaml`, seed 42, 3000 ticks) :
**58,4 → 99,7 ticks/s = ×1,71**. Un peu sous l'estimation Amdahl (×2,0) à cause du
gather/`tolist` ; le profil confirme le nouveau régime : `decide()`/forward NEAT
**45 %** (le plafond), `batch_sense` **31 %** (appelé 1×/tick au lieu de P×),
`eat()` **15 %**. Le forward pass hétérogène est désormais le goulot — plafond
honnête de la vectorisation sans toucher à la topologie NEAT.

`eat()` (15 %) reste batchable mais **volontairement laissé de côté** : gain
marginal (~×1,2) pour un vrai changement sémantique (résolution simultanée des
conflits de capture), alors que le forward pass domine maintenant. Non rentable.

### Invariants — à préserver explicitement
- **n°2** énergie/tick, **n°5** sorties égocentriques, **n°4** tri topo caché :
  intacts (le forward reste par agent, inchangé).
- **n°7** renderer : `sense()` alimente `agent.last_senses` (lu par le renderer).
  Le batch doit **re-scatter** chaque ligne de la matrice dans `agent.last_senses`.
- Reproduction (étape 4, 8 %) : inchangée, hors hotspot.

### Architecture d'implémentation (incrémentale, risque maîtrisé)
Ne **pas** refondre en struct-of-arrays d'un coup. Étape minimale :
garder les objets `Agent`, ajouter un chemin `Population.batch_sense()` qui
*gather* les arrays (x, y, heading, energy) au début du tick, calcule la matrice,
*scatter* `last_senses`, et renvoie les lignes à `network.activate()` par agent.
Le spike **inclut déjà** ce gather/scatter et tient le ×9,8 → surcoût acceptable.
Phases C/D vectorisées et refonte SoA = étapes ultérieures optionnelles.

### Validation comportementale — PASSÉE
Campagne 3 seeds × 12 000 ticks, **même code ancien vs nouveau** (via le levier 1),
`config/default.yaml`, % fourrageurs r>0,1 :

| Seed | Ancien (par agent) | Nouveau (batché) | Δ |
|------|:---:|:---:|:---:|
| 42   | 89 % | 83 % | −6 |
| 7    | 69 % | 68 % | −1 |
| 123  | 40 % | 44 % | +4 |
| moy  | 66 % | 65 % | −1 |

Dans le bruit run-à-run (les audits voyaient déjà seed 123 osciller 42–56 %).
**Aucun seed ne s'effondre**, le fourrage dirigé robuste sur les 3 seeds survit,
le plus faible s'améliore même. Rien à voir avec les mécanismes réducteurs
(crossover : −28 sur un seed). Wall-clock de la campagne : **261,6 s → 153,7 s
= ×1,70**, confirmant que L2 compose avec L1 dans le runner parallèle.

### Statut : **implémenté + validé**. `src/agent.py::batch_sense`, tick « geler
puis percevoir » dans `simulation.py`, 4 tests d'équivalence (`tests/test_batch_sense.py`).

---

## Combiné & bilan  ✅ les deux leviers livrés

Les deux leviers **se composent** et sont mesurés ensemble sur la campagne de
validation (3 seeds × 12k, `default.yaml`) :

| Régime | Wall-clock | Gain vs séquentiel ancien |
|---|---:|---:|
| Ancien, séquentiel (estim. 3×12k/58 t/s) | ~10,3 min | ×1 |
| Ancien + L1 (seeds parallèles) | 4,4 min | ×2,4 |
| Nouveau + L1 + L2 (batché + parallèle) | **2,6 min** | **×4,0** |

Soit **~×4 mesuré** sur la boucle de recherche (l'estimation ×6 supposait L2 ×2,5 ;
le réel est ×1,71 car le forward NEAT domine plus tôt que prévu — honnête et
attendu). Extrapolé à une campagne 30k : ~26 min → **~6–7 min**.

**Ce qui reste hors périmètre** (renoncerait à l'esprit NEAT du projet) :
- `eat()`/`move()` vectorisés : gain marginal, non rentable (voir Levier 2).
- Le **forward pass hétérogène** (45 % du tick) est le plafond dur — le batcher
  imposerait une topologie fixe, donc l'abandon de l'évolution structurelle
  (cf. discussion GPU). C'est la limite de fond, assumée.
