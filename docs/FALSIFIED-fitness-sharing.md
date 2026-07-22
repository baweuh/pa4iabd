# Fitness sharing NEAT — FALSIFIÉ (2026-07-09)

**Status** : ✅ COMPLET — falsification confirmée, non promu, `default.yaml` inchangé.

> *Document créé le 2026-07-22 (audit de cohérence). Ce levier était l'un des 13
> écartés du projet mais n'avait aucun document dédié — et il était même absent
> de `PLAN.md`, pourtant source of truth. Contenu repris de `docs/SYNTHESE.md`,
> sans ajout.*

## Contexte & hypothèse

Chantier n°1 de la feuille de route recherche. Constat de départ :
`src/speciation.py` calculait déjà `compatibility_distance` et `count_species`,
mais **uniquement** pour la colonne CSV et le choix de partenaire de crossover —
jamais pour la sélection elle-même. Le **fitness sharing** est pourtant le
mécanisme par lequel NEAT canonique (Stanley & Miikkulainen 2002) protège
l'innovation structurelle : une espèce nombreuse voit la fitness de ses membres
divisée par sa taille, ce qui empêche une lignée dominante de monopoliser la
reproduction avant qu'une innovation naissante ait eu le temps de se raffiner.

**Hypothèse** : protéger les jeunes espèces laisse le temps aux innovations
structurelles (neurones cachés) d'émerger, donc améliore le fourrage.

## Implémentation

- **`speciation.assign_species(genomes, config) -> list[int]`** : même
  clustering glouton que `count_species`, mais renvoie l'id d'espèce par génome
  au lieu du seul décompte. `count_species` a été refactorée pour la réutiliser
  — zéro duplication de logique.
- **`SpeciationConfig.fitness_sharing: bool = False`** — off = comportement
  legacy **identique bit à bit**, aucun coût ajouté sur le chemin par défaut.
- **`Simulation._priority_fn`** : quand le levier est actif, la clé de tri de
  priorité de reproduction (énergie ou crédit de fourrage cumulé) est divisée
  par la taille de l'espèce de l'agent — `f'_i = f_i / |espèce_i|`, la formule
  canonique. Branché dans `_reproduce_by_energy` **et** `_reproduce_by_foraging`.
  Le crédit réellement dépensé à la naissance n'est **pas** modifié : seul
  l'ordre de priorité pour les slots rares change.

**Config test** : `config/lever_fitness_sharing.yaml` (isolée à cette variable).

**Tests** : 6 ajoutés — `assign_species` seul, plus une preuve d'intégration
(une espèce isolée de taille 1 bat une espèce dominante de taille 2 sur fitness
partagée alors qu'elle perd sur fitness brute) et sa réciproque
(`fitness_sharing: false` préserve l'ancien comportement dans le même scénario).
154 tests verts, pylint 10/10.

**Perf** : 18,02 ticks/s contre 18,04 sans — le calcul d'espèces ne tourne que
dans la branche `slots > 0`, donc rarement à pleine capacité. Le recalcul
périodique anticipé n'a pas été nécessaire.

## Résultat — campagne 3 seeds / 15k

| Seed | Contrôle | Fitness sharing | Δ | neurones cachés moy. (ctrl→FS) |
|------|:---:|:---:|:---:|:---:|
| 42   | **86 %** | 58 % | **−28** | 0,05 → **0,80** |
| 7    | 77 %     | 73 % | −4      | 0,13 → **0,97** |
| 123  | 42 %     | 46 % | +4      | 0,10 → **0,23** |
| **moyenne** | **68 %** | **59 %** | **−9** | |

## Diagnostic — le mécanisme a marché, l'hypothèse était fausse

C'est un résultat inhabituel et instructif : **le levier fait exactement ce
qu'il promettait, et ça n'aide pas.**

L'innovation structurelle est bel et bien protégée — les neurones cachés moyens
passent de 0,05 à 0,80 sur le seed 42, de 0,13 à 0,97 sur le seed 7, soit un
ordre de grandeur. Le mécanisme fonctionne. **Mais la structure ainsi préservée
n'améliore pas le fourrage.**

C'est la confirmation d'un enseignement déjà tiré du volet crossover de poc2.3 :
*les neurones cachés ne discriminent pas* dans cette tâche — ils sont présents
chez les bons comme chez les mauvais fourrageurs. Protéger leur émergence
protège donc du bruit autant que du signal.

**Signature d'opérateur MOYENNANT**, identique au crossover : aide marginalement
le maillon faible (123 : +4) mais écrase le gagnant historique (42 : −28),
tirant tous les seeds vers ~50-70 % et faisant baisser la moyenne. Ne franchit
pas le critère « 3/3 robuste » établi par `apple_repro_bigpop`.

## Verdict

`speciation.fitness_sharing` reste **`false`** dans `config/default.yaml`.
Mécanisme gardé câblé et testé comme référence. `assign_species` reste utile
indépendamment (instrumentation).

**4ᵉ mécanisme réducteur falsifié du projet** — et le premier dont on peut
montrer que l'effet visé a été obtenu sans que le résultat suive.

## Traçabilité

⚠️ Campagne antérieure au correctif `f070f64` (2026-07-15 16:16) :
`tools/campaign.py` n'ouvrait pas le CSV logger, **aucune donnée brute n'a été
conservée** (les 23 dossiers `logs/2026-07-09_*/` ne contiennent que des
`best_genome.json`). Le simulateur étant déterministe, la campagne est
ré-exécutable à l'identique (`config/lever_fitness_sharing.yaml`, 3 seeds, 15k).
Voir la note de traçabilité de `docs/SYNTHESE.md` §6.
