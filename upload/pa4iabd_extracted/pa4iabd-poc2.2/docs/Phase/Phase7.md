# Phase 7 — Renderer Pygame + UI interactive

## Contexte

Phase 6 produit une Simulation stable (98 tests, headless 500 ticks OK).
Phase 7 ajoute la visualisation et le contrôle utilisateur via Pygame.

**Architecture clé** : Renderer wraps Simulation (Approche B).
Phase 6 reste 100% inchangée et testable sans Pygame.

## Spécifications

### 1. Classe Renderer

```python
class Renderer:
    def __init__(self, config: SimConfig)
    def run(self) -> None  # Main loop, gère Pygame + input + render
```

- Lance une fenêtre Pygame (config.render.window_width × window_height)
- Crée une Simulation interne (`self.sim`)
- Boucle fixe : 60 FPS écran, N ticks simulés par frame (N = ticks_per_frame)
- Capture input clavier/boutons UI, met à jour ticks_per_frame
- Affiche HUD + agents + pommes + raycasts + gradient couleur

### 2. Raycasts — Toujours visibles

Pour chaque agent vivant, tracer une fine ligne (1px, alpha=0.5) de son centre vers chaque intersection raycast.

```
Agent (centre) ──────> intersection raycast (16 rayons)
                       |
                       └─ Couleur par type: 
                          - mur: cyan
                          - pomme: orange
                          - vide (max_distance): grey light
```

### 3. Gradient couleur agents par énergie

```
Énergie / max_energy :
  0.0 → 1.0 (rouge)   [RGB 255, 0, 0]
  0.5 → 0.75 (jaune)  [RGB 255, 255, 0]
  1.0 → vert          [RGB 0, 255, 0]
```

Chaque agent : cercle (rayon = config.agent.radius), couleur interpolée selon son énergie actuelle.

### 4. Pommes

Cercles rouges (config.apple.radius), opaques. Les pommes pending (_pending) ne s'affichent pas.

### 5. Zone pénalité murale

Gradient de pénalité visible : bande semi-transparente autour des murs (grise, alpha variant avec distance).

### 6. UI — Boutons interactifs

Boutons cliquables en haut de l'écran:

```
[◄◄] [◄] [Play/Pause] [►] [►►]  |  Speed: 1x
```

- `◄◄` : ticks_per_frame ÷ 2 (min 1)
- `◄` : ticks_per_frame ÷ 2 (min 1)
- `Play/Pause` : toggle boucle simulation (continue ou s'arrête)
- `►` : ticks_per_frame × 2 (max 32 ou 64)
- `►►` : ticks_per_frame × 2 (max 32 ou 64)

Afficher texte `Speed: Nx` en temps réel.

**Clavier alternatif** (bonus):
- `SPACE` : pause/play
- `+` : ×2
- `-` : ÷2
- `ESC` : quit

### 7. HUD (en bas à gauche)

```
Population: 27/30 | Food: 27/30 active
Best fitness: 4.2 | Tick: 12450 | Speed: 4x
```

- Population actuelle vs initial_size
- Nourriture active (len(env.apples))
- Best genome fitness (tracker de sim)
- Tick counter (sim.tick_count)
- ticks_per_frame actuel

### 8. Tests

- `test_renderer_smoke_500_ticks_with_ui.py` :
  - Renderer crée Simulation, tourne 500 ticks sans crash
  - Vérifie que agents rendus ≠ 0, food > 0
  - Pas d'import erreur Pygame
  
- Pas de test unitaire Pygame (c'est graphique), juste smoke.

## Dépendances

- Phase 6 Simulation inchangée
- `pygame` + `numpy` pour interpolation couleur
- Config YAML importe `render` (window_width, window_height) — vérifier dans default.yaml

## Points clés

1. **Isolation** : Renderer n'accède à Simulation que via `self.sim.agents`, `self.sim.env`, `self.sim.tick()`. Zéro modification de Phase 6.
2. **Performance** : Les raycasts tracer à chaque frame doit rester smooth (60 FPS). Si besoin, cache raycasts du dernier tick.
3. **Gradient** : Interpoler RGB progressivement, pas d'à-coups (fonction lisse energy→color).
4. **Boutons** : Détection collision souris + click. Framework simple (pas PyGame-GUI si possible).

## Vérification

- `python -m pytest tests/ -q` → tous les tests Phases 1–6 verts + nouveau smoke
- `pylint src/renderer.py` → 10.00/10
- `black src/renderer.py`
- Smoke visuel 500 ticks : pop et food varient, raycasts dansent, couleurs changent, boutons répondent

## Hors périmètre (Phase 7)

- Enregistrement vidéo / screenshot
- Statistiques détaillées (histogramme âges, etc.)
- Import/export état mid-run
