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

## Levier 2 — Tick vectorisé sur la population  ⚙️ prototypé (spike), à implémenter

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

### Chiffres mesurés (spike `spike_batch_perception.py`)
Sur un snapshot évolué (pop 400, 16 rayons) :
- **Équivalence bit-à-bit** avec `sense()` par agent : `max |Δ| = 0,00e+00`.
- Perception : **15,2 ms → 1,6 ms par tick = ×9,8**.

Estimation Amdahl sur le tick complet (perception ×9,8, forward inchangé) :
57 % → 5,8 %, reste 43 % → tick à ~49 % de l'original ≈ **×2,0**. En batchant
aussi `eat()` (phase D vectorisée, 12 %→~2,4 %) : **~×2,5**, soit **58 → ~145 ticks/s**.
Le forward pass hétérogène (23 %) devient alors le nouveau goulot — c'est le
**plafond honnête** de la vectorisation sans toucher à la topologie NEAT.

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

### Risque principal — validation obligatoire
Nos verdicts sont **sensibles au régime**. Le delta « perception sur snapshot
figé » doit être validé : rejouer la campagne verdict 3 seeds (via le levier 1 !)
et confirmer que le % de fourrageurs par seed reste **dans le bruit** vs baseline.
Si les chiffres bougent, c'est un **résultat à caractériser**, pas forcément une
régression — mais ça doit être tranché avant de promouvoir le nouveau tick.

### Statut : spike validé (équivalence + gain). Implémentation = prochain pas.

---

## Combiné & séquencement

Les deux leviers **se composent** : L1 parallélise les seeds, L2 accélère chaque
tick. Campagne 3 seeds 30k : ~26 min → (L1 ×2,64) ~10 min → (+L2 ×2,5) **~4 min**,
soit **~×6** sur la boucle de recherche (léger abattement possible : contention
mémoire NumPy sous 3 process — à re-mesurer combiné).

**Ordre recommandé :**
1. **L1 déjà livré** — s'en servir tout de suite pour toutes les campagnes.
2. **L2 en 2 temps** : (a) geler+batcher la perception + re-scatter `last_senses`,
   valider l'équivalence par run puis la campagne verdict 3 seeds (avec L1) ;
   (b) une fois validé, vectoriser `eat()`/`move()` pour le reste du gain.
3. Le forward pass hétérogène reste le plafond — hors périmètre (impliquerait de
   renoncer à l'évolution structurelle NEAT, cf. discussion GPU).
