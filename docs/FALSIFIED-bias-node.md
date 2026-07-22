# Nœud de biais NEAT — FALSIFIÉ (2026-07-10)

**Status** : ✅ COMPLET — falsification confirmée, non promu, `default.yaml` inchangé.

> *Document créé le 2026-07-22 (audit de cohérence). Ce levier était l'un des 13
> écartés du projet — et, jusqu'à HyperNEAT, celui qui détenait la **pire
> régression** — mais il était le seul de sa catégorie à n'avoir aucun document
> dédié : ses chiffres ne vivaient qu'en prose dans `PLAN.md` et
> `docs/SYNTHESE.md`. Contenu repris de ces deux sources, sans ajout.*

## Contexte & hypothèse

Point n°5 de la feuille de route recherche. Le **nœud de biais** est un élément
canonique de NEAT (Stanley & Miikkulainen 2002) : une source d'entrée
constamment à 1.0, connectée aux nœuds du réseau, qui permet au réseau
d'apprendre un décalage (offset) indépendamment de ses entrées sensorielles.
Son absence était une **différence documentée** entre l'implémentation du projet
et le NEAT canonique.

**Hypothèse** : ajouter le biais manquant rapproche l'implémentation de la
littérature et devrait, au minimum, ne pas nuire — le réseau reste libre de
mettre ce poids à zéro s'il ne sert pas.

## Implémentation

**Paramètre** : `genome.bias_enabled` (bool, `false` = legacy byte-identique).

Quand il est activé, une source constante `1.0` est câblée à **chaque sortie**
dès la genèse du génome fondateur, exactement comme une entrée sensorielle
supplémentaire — poids initiaux tirés dans `±weight_init_range`, puis soumis
aux mêmes mutations que les autres.

**Config test** : `config/lever_bias.yaml` (isolée à cette seule variable).

**Tests** : mécanisme câblé + testé comme référence. 181 tests verts,
pylint 10/10. Un **bug latent** de `add_connection` (repli en sens inverse) a
été trouvé et corrigé au passage.

## Résultat — campagne 6 seeds / 15k

| seed | 42 | 7 | 123 | 1 | 5 | 99 | **moy** |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| défaut | 86 | 91 | 55 | 27 | 87 | 25 | **62** |
| biais | 13 | 13 | — | 30 | 30 | 41 | **28** |
| Δ | **−73** | **−78** | — | +3 | **−57** | +16 | **−34** |

**Moyenne 62 % → 28 % (−34).** À la date de la campagne, c'était la **pire
régression du projet** — record depuis repris par HyperNEAT V1 (−52).

Le profil est net et asymétrique : **effondrement des seeds forts**
(42 : 86→13 ; 7 : 91→13 ; 5 : 87→30) contre un léger mieux sur deux seeds
faibles (1 : 27→30 ; 99 : 25→41). Le levier ne « déplace » pas la performance,
il l'écrase par le haut.

## Diagnostic

Le biais injecte dans les 2 sorties un **décalage constant et non
situationnel**, présent dès la naissance et jamais annulé par une moyenne
d'entrées sensorielles. Or les sorties sont égocentriques (invariant n°5) :
`output[0]` pilote la vitesse, `output[1]` le virage. Un terme constant sur
`output[1]` produit donc un agent qui **tourne en permanence** dans le même
sens, quelle que soit la perception — et le signal réactif porté par les 16
rayons doit « lutter » contre ce décalage au lieu de piloter directement.

C'est la même famille de mécanisme que les volets 5 et 6 de poc2.3 (capteur 67,
génome sparse) : **ajouter une source au génome fondateur élargit la surface de
mutation initiale et casse la robustesse**. En pire ici, parce que le signal
ajouté est **permanent** plutôt que situationnel.

## Verdict

`genome.bias_enabled` reste **`false`** dans `config/default.yaml`. Mécanisme
gardé câblé et testé comme référence.

**Enseignement de portée générale** : un élément « canonique » de la
littérature n'est pas transposable sans examen du **repère de sortie**. Le NEAT
canonique de Stanley & Miikkulainen ne pilote pas des sorties égocentriques
continues ; le biais y a un rôle différent. Le projet a plusieurs fois vérifié
la même leçon (crossover, HyperNEAT) : reprendre un mécanisme de la littérature
sans l'adapter au domaine ne fonctionne pas.

## Traçabilité

⚠️ Campagne antérieure au correctif `f070f64` (2026-07-15 16:16) : `tools/campaign.py`
n'ouvrait pas le CSV logger, **aucune donnée brute n'a été conservée**. Le
simulateur étant déterministe, la campagne est ré-exécutable à l'identique
(`config/lever_bias.yaml`, 6 seeds, 15k, ~20 min). Voir la note de traçabilité
de `docs/SYNTHESE.md` §6.
