# Historique du projet ALife Neuroevolution — corpus consolidé

> **Ce dossier est un export historique dense et auto-suffisant de la partie
> science/simulation du projet** (la partie de Robin). Il rassemble en un seul
> endroit tout ce qui a été fait, tenté, falsifié et promu, avec les intentions,
> les chiffres et les diagnostics — pour servir de source unique à la fois à un
> mémoire écrit, à un support de soutenance orale et à une référence consultable.
>
> Rédigé le 2026-07-23 à partir du corpus primaire (`PLAN.md`, `docs/SYNTHESE.md`,
> les `docs/RESULTS-*`, `docs/FALSIFIED-*`, `docs/DIAGNOSTIC-*`, `docs/Audits/*`,
> `docs/Phase/*`) et de l'analyse directe du dépôt git. **Additif** : aucun
> fichier existant n'a été modifié ni supprimé.
>
> ⚠️ **Commit retardé d'un jour** (bug de session) : rédigé le 2026-07-23,
> committé le 2026-07-24. Contenu vérifié intact entre les deux — détail en
> `02-CHRONOLOGIE-GIT.md` §7.

---

## Comment lire ce dossier

Les chapitres suivent l'ordre chronologique du projet (qui est aussi l'ordre des
branches git). Chaque chapitre de branche a la **même structure** —
*Intention → Ce qui a été fait → Résultats chiffrés → Diagnostic/Leçon →
Verdict* — pour que la fusion avec la partie du collègue se fasse sans friction.

| Fichier | Contenu | Rôle |
|---|---|---|
| `00-INDEX.md` | Ce sommaire + le point de raccord collègue + le récap des 17 leviers | Entrée |
| `01-INTENTION-ET-PARADIGME.md` | Le POURQUOI : question de recherche, paradigme ALife/NEAT, la contrainte « aucun framework ML », les invariants comme choix scientifiques | Cadre |
| `02-CHRONOLOGIE-GIT.md` | L'analyse git : 115 commits, topologie des branches, backbone daté, commits-clés commentés | Carte temporelle |
| `03-FONDATIONS-Phases-1-8.md` | Le socle technique (master → poc2.1) : config, génome, réseau, environnement, agent, sim, rendu | Architecture |
| `04-poc2.2-EMERGENCE.md` | Le cœur : diagnostic « ça survit mais ça n'apprend pas », les 5 correctifs, la 1ʳᵉ émergence robuste | Percée fondatrice |
| `05-poc2.3-CAPTEURS-ET-STRUCTURE.md` | Capteurs 67, viz réseau, crossover, fitness sharing, sparse — les 6 volets | Relances structurelles |
| `06-poc2.4-CAMPAGNES.md` | Le pic : perf ×4, novelty / densité / K-sweep (promus), biais / archive / critère minimal / troncature / îles (falsifiés), instrumentation | Campagnes de falsification |
| `07-poc2.5-HYPERNEAT.md` | Encodage indirect CPPN→substrat, V1→V4, impasse honnête | Encodage indirect |
| `08-poc3-ECHELLE.md` | L'hypothèse d'échelle : archi livrée, hypothèse **jamais tranchée** = la limite assumée du travail | Axe sans verdict |
| `09-poc2.6-PLASTICITE-ET-VARIATION.md` | Hors sélection : sigma auto-adaptatif + plasticité Hebbienne, tués par le même budget d'événements | Régime de variation & intra-vie |
| `10-BILAN-LEVIERS.md` | Le tableau maître des 17 leviers (13 écartés + 4 promus) + les 3 limites assumées | Annexe/synthèse |
| `11-METHODE-LECONS-TRANSVERSES.md` | La méta-histoire : la méthode par falsification, les leçons transverses, les erreurs d'audit rattrapées | Le vrai storytelling |

---

## Le projet en une phrase

Un écosystème artificiel où des agents apprennent à se nourrir **par évolution
seule** (NEAT écrit à la main, sans framework ML), et une enquête méthodique de
deux mois pour savoir **pourquoi le fourrage dirigé n'émerge pas spontanément**,
puis **par quels mécanismes** on peut le faire émerger de façon robuste.

**Fil rouge unique** : *le fourrage dirigé est trop faiblement sélectionné pour
être un attracteur stable* — on ne le corrige jamais par un réglage de
paramètre, seulement en changeant le **mécanisme** (couplage sélection↔compétence
+ faible dérive).

**Résultat bout-en-bout** : de **52 % à 79 % de fourrageurs** (moyenne 6 seeds)
entre le défaut de poc2.3 et le défaut de clôture, obtenu par 4 leviers promus,
au prix de 13 leviers falsifiés (chacun enterré avec sa preuve).

---

## Les 17 leviers en un coup d'œil

**4 promus** (tous *additifs*, tous liés à l'échelle ou à l'écologie) :

| Levier | Branche | Gain | Chapitre |
|---|---|---|---|
| Repro ∝ pommes cumulées **+** population 200→400 | poc2.2 | la percée fondatrice (1ʳᵉ émergence robuste+stable) | `04` |
| Novelty search (bonus additif) | poc2.4 | 52 → 62 % (**+10**), aucun seed ne régresse | `06` |
| Densité — carte ×√2 + `max_speed` ÷2 | poc2.4 | 62 → 66 % (**+4** @30k) | `06` |
| K-sweep — `apples_per_offspring` 3.0 → 1.5 | poc2.4 | 66 → 79 % (**+13**), 5/6 seeds montent | `06` |

**13 écartés** (aucun agissant sur le mécanisme de sélection n'a jamais été promu) :

| Levier | Branche | Résultat | Chapitre |
|---|---|---|---|
| Crossover NEAT intra-espèce | poc2.3 | 30 → 65 % (+35) mais non robuste (123 : 28→10) | `05` |
| Crossover + bigpop | poc2.3 | 49 % — sous chaque levier seul | `05` |
| Capteur 67 entrées | poc2.3 | casse la robustesse (123 : 43→1) | `05` |
| Génome fondateur sparse | poc2.3 | 68 → 24 % (**−44**) | `05` |
| Fitness sharing NEAT | poc2.3 | 68 → 59 % (−9) | `05` |
| Archive de nouveauté | poc2.4 | 62 → 55 % (−7) | `06` |
| Nœud de biais NEAT | poc2.4 | 62 → 28 % (**−34**) | `06` |
| Critère minimal de repro | poc2.4 | 66 → 63 % (−3) | `06` |
| Troncature adoucie | poc2.4 | 66 → 65 % (−1), cas mixte | `06` |
| Modèle d'îles | poc2.4 | 79 → 68 % (−11), les 6 seeds régressent | `06` |
| HyperNEAT (V1→V4) | poc2.5 | meilleur = V3 : 79 → 68 % ; V1 −52 | `07` |
| Mutation auto-adaptative (sigma ES) | poc2.6 | falsifié au diagnostic (dérive pure) | `09` |
| Plasticité Hebbienne (V1+V2) | poc2.6 | falsifié au diagnostic (pile ou face) | `09` |

**Convention de comptage** (sans laquelle le total est ambigu — reprise de
`SYNTHESE.md §6bis`) :
1. les **versions successives d'un même mécanisme** comptent pour un levier
   (HyperNEAT V1→V4, Hebbien V1→V2, plafond plat + round-robin) ;
2. les **réglages purement paramétriques** de poc2.2 (mutation, drain,
   `max_energy`, densité de nourriture, `move_cost`) ne comptent pas — calibration,
   pas mécanisme (sinon ~8 falsifications de plus) ;
3. « carte agrandie seule » n'est pas un levier écarté : c'est la **première
   moitié** du levier densité, finalement promu sous la forme « carte + vitesse ÷2 ».

---

## Raccord avec la partie web/infra (pour le collègue)

Cette moitié du projet (Robin) est **100 % science/simulation**. La partie du
collègue — faite « en sous-marin » — est l'**intégration web / infrastructure**,
et elle est identifiable dans le dépôt :

- **Branches git dédiées** (voir `02-CHRONOLOGIE-GIT.md`) : `origin/web-integration`,
  `origin/update-web`, `origin/poc2.4-web-integration`. Leurs commits sont
  authorés **sur une autre machine, en fuseau UTC (+0000)** — commits
  `fa7434a` (« Initial commit », 2026-07-07), les trois commits à nom d'UUID
  (`153fa94`, `6b8332a`, `13cd06c`), `a0cce84` (« added web integration »),
  `ee6ce2c` / `84d84ae` (« merged main project into web »), `fb67a90`
  (« removed unused files »), `e33c957` (« merge of poc2.4 and update-web »).
- **Phase 9 (AWS + Dashboard)**, marquée « ⛔ HORS PÉRIMÈTRE » dans `PLAN.md`
  côté science, avec la mention explicite « infrastructure gérée par un collègue
  de Robin » (convenu 2026-07-15) : S3 (upload ZIP + génomes), DynamoDB
  (métriques), Amplify (dashboard). **C'est très probablement le périmètre du
  collègue.**

**Points d'insertion naturels pour la fusion** :
- la **chronologie git** (`02`) est la carte temporelle commune : les branches
  web s'y posent aux dates indiquées (juillet 6-11 pour l'essentiel) ;
- l'**état du déploiement / dashboard** vient compléter le chapitre `03`
  (architecture) et le chapitre `06` (les campagnes produisaient les données que
  le dashboard consomme) ;
- le storytelling fusionné peut opposer/associer les deux fils : « la science
  cherchait pourquoi ça n'évolue pas » / « l'infra rendait les résultats
  observables et partageables ».

**Ce dossier ne documente PAS la partie du collègue** — il se contente d'en
marquer le raccord. Le collègue produit sa propre moitié, puis fusionne (c'est
lui qui pilote la fusion).

---

## Checklist de complétude (vérification interne)

Les 17 leviers du tableau ci-dessus sont chacun traçables vers un chapitre :
- poc2.2 : levier promu #1 → `04`
- poc2.3 : leviers écartés crossover, crossover+bigpop, capteur 67, sparse,
  fitness sharing → `05`
- poc2.4 : promus novelty/densité/K-sweep + écartés archive/biais/critère
  minimal/troncature/îles → `06`
- poc2.5 : HyperNEAT V1→V4 → `07`
- poc2.6 : sigma ES + Hebbien → `09`
- poc3 (hors comptage des 17 — axe sans verdict) → `08`
