---
Task ID: 1
Agent: main
Task: Port de la simulation ALife (Python/Pygame) vers Next.js (TypeScript/Canvas 2D)

Work Log:
- Analysé les 7 fichiers source Python (config, genome, network, environment, agent, simulation, renderer)
- Identifié le problème racine : pygame-ce ne supporte pas le rendu canvas dans Pyodide
- Porté l'intégralité du code en TypeScript pur (6 fichiers dans src/lib/alife/)
- Créé un renderer Canvas 2D qui remplace Pygame
- Créé la page Next.js avec landing page, simulation canvas, HUD et contrôles
- Vérifié dans le navigateur agent : compilation OK, simulation tourne, contrôles fonctionnent, 0 erreur console

Stage Summary:
- Fichiers créés : config.ts, genome.ts, network.ts, environment.ts, agent.ts, simulation.ts, page.tsx
- L'approche Pyodide+pygame a été remplacée par du JavaScript pur + Canvas 2D
- Toute la logique NEAT est préservée : mutations, crossover, spéciation, tournoi, injection
- La simulation fonctionne dans le navigateur sans dépendance externe (pas de Pyodide)