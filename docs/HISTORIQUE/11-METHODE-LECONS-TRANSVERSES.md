# 11 — Méthode et leçons transverses : la méta-histoire

> Le chapitre du **storytelling**. Ce qui fait la valeur du projet n'est pas un
> « grand résultat » unique, mais la **qualité de son raisonnement de
> falsification** et les leçons transverses qui en émergent. C'est le fil à
> dérouler pour un mémoire ou une soutenance. Sources : tout le corpus, en
> particulier `SYNTHESE.md §6` et les deux audits de clôture de poc2.6.

---

## 1. La méthode : falsifier, une variable à la fois, avec un diagnostic

Le projet fonctionne comme un **journal de recherche popperien**. Chaque levier
suit le même protocole :
1. **Hypothèse explicite** (souvent adossée à la littérature : Lehman & Stanley,
   Soros & Stanley, Stanley et al., Corus et al.).
2. **Isolation à une variable** : le levier = une seule différence depuis le
   contrôle (rendu possible par l'invariant « zéro nombre magique » — tout est en
   config).
3. **Campagne multi-seeds** (3 puis 6 seeds, 15k puis 30k ticks) mesurée au bon
   yardstick (les sondes `steer_probe`/`run_and_probe`, pas le % de survie).
4. **Verdict + diagnostic mécanistique** : jamais « ça marche pas », toujours
   *pourquoi* — souvent vérifié empiriquement (ex. HyperNEAT : `steer_score` = 0,0
   sur 74/100 CPPN fondateurs, pas juste un mauvais score de campagne).
5. **Code conservé** (câblé + testé) même quand falsifié, comme référence
   d'expérience.

**Résultat de méthode** : 13 leviers enterrés, chacun avec sa preuve, et un fil
rouge qui se **renforce** à chaque échec au lieu de s'effriter.

---

## 2. Le fil rouge, énoncé et vérifié

> *Le fourrage dirigé est trop faiblement sélectionné pour être un attracteur
> stable — on ne le corrige jamais par un réglage de paramètre, seulement en
> changeant le mécanisme (couplage sélection↔compétence + faible dérive).*

Ce fil est **posé** en poc2.2 (diagnostic), **validé positivement** par la percée
(repro ∝ pommes + bigpop), puis **confirmé négativement** à chaque falsification.
Sa forme prédictive la plus nette :
- **les leviers réducteurs échouent** (crossover, fitness sharing, capteur 67,
  sparse, biais, archive, îles) — ils *moyennent* au lieu d'*amplifier* ;
- **les leviers additifs réussissent** (population, novelty, densité, K) — ils
  élèvent tous les seeds ensemble.

Le pattern est devenu **prédictif** : dès poc2.3, on pouvait anticiper qu'un
nouveau réducteur échouerait. La nouveauté (poc2.4) est la première validation
*positive* et prédictive de ce cadre.

---

## 3. Les leçons transverses (les vraies punchlines)

### A. La sensibilité chaotique aux effets fondateurs
Le simulateur est **déterministe** mais **chaotique** vis-à-vis de l'ordre des
naissances : le diagnostic tick-par-tick de la troncature (seed 123) montre que
deux configurations sont **identiques bit à bit** jusqu'à ce que la population
atteigne `max_size`, puis **divergent** dès qu'une vraie compétition multi-agents
apparaît (l'ordre des naissances change l'ordre de consommation du RNG des
mutations → cascade). **Ce n'est pas un bug** — c'est la signature d'un régime où
la dérive fondatrice pèse lourd. C'est *le même phénomène* que « chaque réglage de
poc2.2 rebrasse quel seed gagne ».

### B. Le profil « moyennant » des réducteurs
Crossover, fitness sharing, archive : tous **réduisent la variance inter-seeds**
(rapprochent tout le monde de ~50 %) en mélangeant vers le comportement moyen de la
population. Ils aident parfois le maillon faible (+quelques points) mais écrasent
toujours les gagnants (−beaucoup). **Protéger la structure** (fitness sharing fait
exploser les neurones cachés) **ne sert à rien** si la structure ne discrimine pas
la tâche — *le signal est le comportement, pas la structure*.

### C. La parcimonie de la tâche (~3 événements/agent) comme limite structurelle
Le résultat le plus profond, découvert en poc2.6 : **la tâche ne fournit que de
l'ordre de 3 événements informatifs par agent** (~3 pommes par vie, ~3 générations
de profondeur de lignée). Cela tue **deux familles entières** de mécanismes d'un
coup :
- tout mécanisme de **second ordre** (sigma auto-adaptatif — sigma n'est
  sélectionné qu'à travers le succès des enfants) ;
- tout mécanisme d'**attribution de crédit intra-vie** (Hebbien — une trace de
  ~100 ticks pour ~3 récompenses = du bruit).

**C'est un critère réutilisable** : avant tout levier qui doit *accumuler du
signal*, compter les événements informatifs par agent. Si c'est ~3, le levier est
mort-né — indépendamment de son réglage.

### D. Le déterminisme comme filet de sécurité scientifique
Le simulateur est strictement déterministe (réseau feedforward = fonction pure,
pas de récurrence, RNG seedé). Conséquence : **un log manquant coûte du temps de
calcul, pas la vérité du résultat** — on peut toujours rejouer. Vérifié deux fois
(voir §4). C'est une propriété qui distingue ce projet d'une expérience physique
dont une donnée perdue l'est définitivement.

---

## 4. Les erreurs d'audit rattrapées (l'honnêteté du corpus)

Le double audit de clôture (2026-07-22) est lui-même une partie de l'histoire : le
projet **a audité ses propres résultats et corrigé ses propres erreurs** avant
soutenance. Deux audits indépendants (cohérence documentaire + traçabilité
scientifique).

### Cohérence documentaire — 46 constats, 22 bloquants
Corrigés notamment : 5 chiffres faux dans `FALSIFIED-min-criterion.md` (dont le
crossover donné à **−15 alors qu'il fait +35**, signe inversé) ; HyperNEAT V3/V4
déclarés « non engagés » alors que le chantier était clos ; « 148 tests » figé
depuis poc2.3 ; README annonçant 33 entrées au lieu de 49 ; et le **surclaim** « les
11 leviers falsifiés agissaient *tous* sur la sélection » (faux — sparse, biais,
capteur 67, HyperNEAT agissent sur le génome/encodage, pas la sélection). Ajout du
**tableau unique des 13 leviers + convention de comptage** (`SYNTHESE.md §6bis`,
repris dans `10`) : le chiffre était affirmé trois fois, listé nulle part.

### Traçabilité scientifique — le trou de ~45 % et le bug `f070f64`
**Le fait, sans détour** : `tools/campaign.py` **n'a jamais appelé
`open_csv_logger()` avant le commit `f070f64` du 2026-07-15 16:16.** Les campagnes
d'avant n'ont écrit **aucune donnée brute** — seul le tableau récapitulatif était
affiché, non redirigé. Part des résultats chiffrés adossés à une donnée brute, par
branche :

| branche | traçabilité | note |
|---|---|---|
| poc2.2 | partielle | diagnostic traçable, percée n'a que ses génomes |
| poc2.3 | ~100 % | sorties `run_and_probe` sauvegardées à la main |
| poc2.4 | **~10 %** | **le trou — contient les 4 leviers promus** |
| poc2.5 | ~90 % | seul chantier citant déjà ses chemins de logs |
| poc2.6 | ~5 % de logs, **100 % ré-exécutable** | sondes + configs versionnées |

**Deux erreurs de FOND corrigées** :
1. **`N_e ≈ 82-90 sur pop 400` était faux** — mesuré en phase de croissance de la
   population (pop 200-350) puis étiqueté « pop 400 ». Vraie valeur **≈ 150**
   (N_e/N ≈ 0,37, médiane sur 10 101 lignes de CSV à pop pleine, 65 runs).
   L'argument survit (la dérive pèse lourd), mais la version publiée était
   **réfutable en ouvrant n'importe quel CSV du dépôt**.
2. **Le critère minimal et la troncature étaient comparés au défaut *pré-densité***
   alors que leurs configs portent la densité — deltas corrigés de +1 → **−3** et
   +3 → **−1** (verdicts inchangés, renforcés).

**Pourquoi ce n'est pas une perte de résultats** : le déterminisme, vérifié deux
fois. (1) Relancer `default.yaml` seed 42 produit un CSV **bit-à-bit identique** au
run archivé. (2) La baseline K=3.0 30k, dont la mesure d'origine n'avait laissé
aucune trace, a été **entièrement rejouée le 2026-07-22** et rend
`85|77|61|58|85|32` → 66 % — **les six valeurs publiées, à l'identique**, sept
jours et deux branches plus tard. Le chiffre le plus exposé (le 79 % du K-sweep) est
aussi le mieux étayé : CSV archivé + recalculé (79,38 %) + baseline rejouée.

### Les leçons d'audit (transposables)
- **Ne jamais caractériser un régime stationnaire sur un run non stabilisé** (le
  N_e mesuré en phase de croissance).
- **Toujours différencier une config de levier vs le défaut *de la même époque***
  (le piège densité).
- **Auditer les RÉSUMÉS en priorité** : ici les docs primaires étaient fiables,
  ce sont les **synthèses** qui mentaient (chiffres recopiés, signes inversés).
- **Un chiffre-titre doit être reconstructible** par un lecteur (d'où le tableau
  des 13 leviers).
- **Toujours un contrôle de harnais + une mesure appariée**, jamais une différence
  de deux moyennes sur métrique bruitée (la leçon Hebbien V2, cf. `09`).

---

## 5. Ce que le projet a démontré, et ce qu'il assume ne pas avoir démontré

**Démontré** :
- On peut faire émerger un fourrage **robuste et stable** par évolution seule —
  mais uniquement par des leviers **additifs/écologiques**, jamais par un réglage
  ni par un mécanisme de sélection sophistiqué.
- Un **fil rouge prédictif** (réducteur = échec, additif = succès) qui a tenu sur
  17 leviers.
- Une **limite structurelle de la tâche** (parcimonie ~3 événements/agent) qui
  explique *pourquoi* les mécanismes de second ordre et d'apprentissage intra-vie
  sont inapplicables ici.

**Assumé non démontré** (les limites, `08` et `10`) :
- **L'hypothèse d'échelle** — jamais tranchée (round 1 confondu, round 2 interrompu
  à 4 %), alors que c'est la direction dont relèvent 4 des 5 leviers promus. Le
  seul grand axe sans verdict.
- **HyperNEAT V5**, **repro non canonique**, **QD/ALPS** — non explorés, chacun
  avec sa raison (impasse close, catégorie qui a échoué, dépendance à l'échelle).

**La force du récit** : un projet qui **sait exactement ce qu'il a montré, ce qu'il
a réfuté, et ce qu'il n'a pas démontré** — et qui a audité et corrigé ses propres
chiffres avant de les présenter. C'est cette honnêteté méthodologique, plus qu'un
score, qui constitue le résultat.
