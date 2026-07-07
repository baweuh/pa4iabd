# Phase 8 — Intégration : main.py + CLI ✅

## Contexte

Phases 1–7 livrées (103 tests, `Simulation` headless-stable, `Renderer` qui
l'enveloppe sans la modifier — invariant n°7). Il manquait le point d'entrée
utilisateur : pas de CLI, `main.py` racine vide, et les commandes `python main.py`
de `CLAUDE.md` non fonctionnelles. Phase 8 finalise le pipeline.

## Décisions architecturales

- **CLI → fallback YAML (invariant n°1)** : `--seed`/`--ticks` ont pour défaut
  `None`. Si omis, la valeur vient de `config.simulation.seed` / `.max_ticks`.
  La CLI ne surcharge la config que si l'argument est explicitement passé. Aucun
  `42`/`0` codé en dur dans `main.py` → le YAML reste la source de vérité.

- **Override de config immuable via `dataclasses.replace`** : `SimConfig` et ses
  sections sont `frozen`. Pour appliquer un override CLI, on reconstruit la
  section `simulation` puis la racine avec `dataclasses.replace`, ce qui rejoue
  `__post_init__` (la validation, dont `max_ticks >= 0`). Pas de mutation, pas de
  re-parse YAML.

- **Logger CSV exposé en API publique (Option 3)** : `Simulation` n'écrivait le
  CSV que dans `run()` (via `_open_csv`/`_log_row`/`_close_csv` privés). Une
  boucle headless manuelle (pour imprimer la progression tous les N ticks) avait
  besoin du CSV sans toucher au privé. On ajoute deux fines méthodes publiques
  `open_csv_logger()` / `close_csv_logger()` qui délèguent au privé. `run()` est
  inchangée. Les tests de Phase 6 migrent vers l'API publique (suppression des
  `pylint: disable=protected-access` correspondants).

- **Indicateur fin de vie piloté par config, pas par nombre magique** : le prompt
  initial écrivait `agent.max_age - 500`, mais `Agent` n'a pas d'attribut
  `max_age`, et `500` serait un nombre magique. Les deux valeurs existent déjà
  dans la config (`config.agent.max_age=5000`, `config.agent.end_of_life_ticks=500`,
  présentes dans `default.yaml`/`AgentConfig`). Le renderer lit
  `self._config.agent.*` → zéro hardcode (invariant n°1).

## Architecture main.py

```
main(argv)
  ├─ build_parser()                 # argparse : --mode/--seed/--ticks/--config
  ├─ parse args
  ├─ garde : --ticks + --mode visual → parser.error (exit 2)
  ├─ resolve_config(path, seed, ticks)
  │     ├─ SimConfig.from_yaml(path)         # ConfigError si absent/malformé
  │     ├─ valide seed >= 0                  # SimulationConfig ne valide pas le signe
  │     └─ dataclasses.replace(...) override seed/max_ticks
  └─ dispatch
        ├─ visual   → run_visual(config)   → Renderer(config).run()
        └─ headless → run_headless(config) → boucle manuelle
```

### Flux argparse / override

| Argument   | Défaut argparse | Si omis                        |
|------------|-----------------|--------------------------------|
| `--mode`   | `"visual"`      | —                              |
| `--seed`   | `None`          | `config.simulation.seed`       |
| `--ticks`  | `None`          | `config.simulation.max_ticks`  |
| `--config` | `default.yaml`  | —                              |

### Boucle headless

`Simulation(config)` (graine = `config.simulation.seed`), `open_csv_logger()`,
puis `tick()` jusqu'à `max_ticks` (0 = jusqu'à extinction / Ctrl+C). Tous les
`logging.log_interval_ticks` (=100, réutilisé — pas de nouvelle constante) :
`Tick: XXXXXX | Pop: XX | Food: XX`. `finally: close_csv_logger()`, puis bannière
finale. `KeyboardInterrupt` est intercepté pour fermer proprement le CSV.

### Gestion d'erreurs

- Fichier config absent/malformé → `ConfigError` capturé, message clair sur
  stderr, code retour 2.
- `--ticks` en mode visual → `parser.error` (exit 2).
- `seed < 0` → `parser.error` (exit 2).
- `--ticks < 0` → rejeté par `__post_init__` via `replace` (`ConfigError`).

## Indicateur fin de vie (renderer)

`_draw_agents()` appelle désormais `_agent_color(agent)` au lieu de
`_energy_color(agent.energy)`. `_agent_color` calcule la couleur énergie puis,
si `agent.age >= max_age - end_of_life_ticks`, interpole linéairement vers
`COLOR_END_OF_LIFE` (rouge) selon `ratio = (age - start) / end_of_life_ticks`
borné `[0,1]`. Avant la zone fin de vie, le gradient énergie est intact.

## Implémentation

- Fichiers :
  - `src/main.py` (NEW, ~120 lignes) — CLI + dispatch.
  - `main.py` racine (shim → `src.main.main`).
  - `src/simulation.py` (+`open_csv_logger`/`close_csv_logger`).
  - `src/renderer.py` (+`COLOR_END_OF_LIFE`, `_agent_color`, un appel modifié).
  - `tests/test_simulation.py` (migration API publique).
  - `tests/test_main_cli_modes.py` (NEW).
- Tests : visual init, headless 500 ticks + CSV, sortie progression, ticks
  invalides en visual, seed négatif, déterminisme graine (3 runs identiques).

## Patterns / Notes

- `main()` retourne un `int` (code retour) ; le shim racine fait
  `raise SystemExit(main())`.
- Fonctions découpées (`build_parser`/`resolve_config`/`run_*`) → testables sans
  subprocess.
- Déterminisme : `Simulation` graine `Random(config.simulation.seed)` et
  `TRACKER.reset()` à la construction → runs reproductibles à graine égale.
- Isolation préservée : `main.py` orchestre ; la seule modification de logique
  hors renderer est l'ajout (non destructif) des deux hooks CSV publics.
