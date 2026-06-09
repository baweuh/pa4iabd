# ALife Neuroevolution Simulation

## Stack
Python 3.10+, Pygame, NumPy, YAML. Aucun framework ML.
pylint + black obligatoires. Commit après chaque module testé.

## Structure
src/genome.py · src/network.py · src/agent.py
src/environment.py · src/simulation.py · src/renderer.py
src/config.py · config/default.yaml · main.py · tests/

## INVARIANTS — violation = bug critique

1. ZÉRO valeur hardcodée. Tout paramètre vient de SimConfig (YAML).
2. Énergie en pommes-équivalent PAR TICK. Jamais par frame.
3. Réseau feedforward uniquement. Avant add_connection(A→B) :
   vérifier DFS qu'aucun cycle créé. Si cycle → essayer (B→A).
   Si toujours cycle → abandonner la mutation.
4. Topological sort calculé UNE FOIS à la création de l'agent (cache).
   Jamais recalculé pendant la vie de l'agent.
5. Vitesse normalisée post-output :
   speed = min(|(vx,vy)|, max_speed)
   direction = (vx,vy) / |(vx,vy)|
6. Pommes spawnent UNIQUEMENT dans la zone safe (hors zone pénalité).
7. Renderer séparé de la logique. simulation.py ne touche pas Pygame.

## Inputs NN : 33
  [0-15]  distance normalisée [0→1] pour chaque raycast
  [16-31] type encodé (0.0=rien, 0.5=pomme, 1.0=mur)
  [32]    énergie normalisée [0→1]

## Outputs NN : 2 → (vx_brut, vy_brut) → normalisés

## Zone pénalité murale
  penalty = zone_max_drain × (1 − dist_mur / zone_width)
  Appliquée si dist_mur < zone_width. Gradient, pas binaire.

## Commandes
  python main.py                  # simulation normale
  python main.py --headless       # sans rendu
  python main.py --config x.yaml  # config custom
  python -m pytest tests/ -v      # tous les tests
  black src/ && pylint src/       # qualité

## Ce que Claude NE doit PAS faire
- Importer neat-python, torch, tensorflow, gym
- Écrire un nombre magique dans le code
- Modifier renderer.py depuis simulation.py
- Ajouter des connexions récurrentes
- Reporter les tests après implémentation