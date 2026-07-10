# Densité agents/pommes — carte agrandie + vitesse réduite, promu en défaut (poc2.4)

> Signalé par Robin en jeu (2026-07-10) : la simulation semble surpeuplée, les
> pommes sont mangées quasi instantanément par accident plutôt que par du
> vrai fourrage dirigé. Confirme et prolonge [[apple-density-signal]]
> (2026-07-09). Journal complet dans `PLAN.md` (branche poc2.4).

## Le symptôme, mesuré

`tools/apple_capture_probe` sur `default.yaml` (novelty inclus), pop pleine
400/400, seed 42, 4000 ticks (warmup 1000) :

- lifetime d'une pomme : **médiane 14 ticks (0,23s)**, seulement 20/160
  pommes vivantes en moyenne (file de respawn saturée).
- **54 %** des captures sans approche dirigée claire (24 % « adjacent » —
  agent déjà collé dessus, zéro trajet réel ; 30 % « undirected »).

Chiffres quasi identiques à l'audit du 2026-07-09 : la promotion de la
nouveauté en défaut n'a rien changé au symptôme (normal, elle agit sur la
sélection, pas sur la densité géométrique agents/pommes).

## Deux mécanismes, deux moitiés du symptôme

- **Densité statique** (combien d'agents sont déjà collés à une pomme au
  moment où elle apparaît) → réduite en agrandissant le monde à population et
  nombre de pommes inchangés (`config/lever_bigmap.yaml`, monde ×√2).
- **Balayage** (combien de terrain neuf un agent couvre par tick, donc la
  fréquence des collisions fortuites en cours de route, indépendamment du
  pilotage) → réduit en divisant `agent.max_speed` par 2
  (`config/lever_bigmap_slow.yaml`, combine les deux).

Sonde directe (carte + vitesse ÷2 vs défaut) : lifetime médiane **14→58
ticks (×4)**, adjacent stable à 12 % (déjà réglé par la carte seule).

**`population.max_size` volontairement JAMAIS touché.** poc2.2 ÉTAPES 7-10
(voir `docs/Audits/AUDIT-poc2.2-v3.md`) ont établi empiriquement qu'une
population plus PETITE (~200) rouvre la dérive fondatrice (variance
inter-seed énorme, un seed bloqué ~14 %) que la grande population (400) a
justement corrigée. `max_size 400` est un des deux piliers du seul régime
robuste+stable connu (`apple_repro_bigpop`, avec `apples_per_offspring`) —
pas un réglage libre à réduire pour désengorger la carte.

## Le verdict — campagnes 6 seeds (`tools/campaign.py`)

### Carte agrandie SEULE (`lever_bigmap.yaml`) — 15k, non promue

| seed | 42 | 7 | 123 | 1 | 5 | 99 | **moy** |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| défaut | 86 | 91 | 55 | 27 | 87 | 25 | **62** |
| carte seule | 95 | 68 | 44 | 37 | 86 | 14 | **57** |

Gain net sur le symptôme direct, mais mitigé à l'évolution : moyenne en
baisse (−5), et le seed le plus faible (99) — censé être le plus aidé — est
en fait le plus dégradé (25→14). Hypothèse : `sensors.max_distance` (283 px)
n'a pas grandi avec le monde, les pommes sont statistiquement plus souvent
hors de portée du raycast.

### Carte agrandie + vitesse ÷2 (`lever_bigmap_slow.yaml`) — 15k

| seed | 42 | 7 | 123 | 1 | 5 | 99 | **moy** |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| défaut | 86 | 91 | 55 | 27 | 87 | 25 | **62** |
| carte+vitesse | 86 | 60 | 48 | 50 | 86 | 17 | **58** |

Toujours sous le défaut à 15k (−4), mais aide nettement un seed dur (1 :
27→50). `record` (pommes du meilleur agent) plus bas que le défaut (25-29 vs
30-36) — hypothèse : des agents plus lents mangent moins par tick, donc la
sélection sur le fourrage a besoin de plus de temps pour se manifester.
Décision Robin : **valider à 30k avant de trancher.**

### Carte agrandie + vitesse ÷2 — 30k (décisif)

| seed | 42 | 7 | 123 | 1 | 5 | 99 | **moy** |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| défaut 30k | 82 | 84 | 76 | 23 | 81 | 27 | **62** |
| carte+vitesse 30k | 85 | 77 | 61 | **58** | 85 | 32 | **66** |
| Δ | +3 | −7 | −15 | **+35** | +4 | +5 | **+4** |

**L'hypothèse se confirme : le levier passe positif avec plus de temps.**
4/6 seeds montent, dont un gain massif sur le seed historiquement le plus
dur (1 : 23→58, +35) ; 2/6 régressent (7, 123) mais modérément. Moyenne
**+4**, et les deux seeds les plus faibles du défaut (1, 99) montent tous les
deux — exactement le profil recherché. Premier levier de densité qui tient
sa promesse aux deux niveaux : symptôme visuel ET benchmark évolutif.

## Promotion

`config/default.yaml` active désormais :
```yaml
world: { width: 3200, height: 1800 }   # ×√2
agent: { max_speed: 2.122 }             # ÷2
```
Population, nombre de pommes, capteurs, réseau : **inchangés**. 182 tests
verts, black clean, pylint stable. `config/lever_bigmap.yaml` (carte seule,
falsifiée) et `config/lever_bigmap_slow.yaml` (référence, absorbée dans
`default.yaml`) conservés comme historique d'expérience.

## Suites possibles

- Vérifier que le gain tient au-delà de 30k (le bigpop seul, poc2.2 ÉTAPE 8,
  avait érodé entre 15k et 30k — pas encore vérifié si ce levier-ci tient à
  60k+).
- Seed 123 régresse (−15) malgré la moyenne positive : pas encore expliqué.
- Le split directed/undirected de la sonde est probablement décalibré pour
  la vitesse réduite (lookback en ticks fixes) — la métrique lifetime reste
  la plus fiable pour ce levier.
