"""
src/renderer.py — Rendu Pygame uniquement. Séparé de la logique pour le mode headless.
CDC §9 : Renderer — Pygame rendering.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from .config import AgentsConfig, EnvironmentConfig, SimulationConfig

if TYPE_CHECKING:
    from .simulation import Simulation


# ── Palette de couleurs ───────────────────────────────────────────────

class Colors:
    BG = (15, 15, 20)
    GRID = (25, 25, 32)
    AGENT = (255, 220, 50)
    AGENT_DYING = (255, 100, 50)        # indicateur vieillesse
    FOOD = (220, 50, 50)
    FOOD_INNER = (255, 120, 120)
    WALL_ZONE = (200, 40, 40, 30)       # zone pénalité (semi-transparent)
    RAY_FOOD = (255, 100, 100)
    RAY_WALL = (100, 130, 255)
    RAY_NONE = (40, 55, 40)
    HUD_FG = (200, 200, 200)
    HUD_HL = (255, 220, 50)
    HUD_BG = (20, 20, 28, 200)


class Renderer:
    """
    Rendu Pygame de la simulation. Séparé de la logique (CDC §9).
    Seulement instancié en mode non-headless.
    """

    def __init__(
        self,
        env_cfg: EnvironmentConfig,
        agent_cfg: AgentsConfig,
        sim_cfg: SimulationConfig,
    ) -> None:
        self.env_cfg = env_cfg
        self.agent_cfg = agent_cfg
        self.sim_cfg = sim_cfg

        self.env_width = env_cfg.env_width
        self.env_height = env_cfg.env_height
        self.zone_width = env_cfg.zone_width
        self.agent_radius = int(agent_cfg.agent_radius)
        self.food_radius = int(agent_cfg.food_radius)

        # HUD panel (à droite de l'environnement)
        self.panel_width = 260
        self.screen_width = self.env_width + self.panel_width
        self.screen_height = self.env_height

        pygame.init()
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))
        pygame.display.set_caption("ALife — Neuroévolution Continue")
        self.clock = pygame.time.Clock()
        # pygame.font.Font(None, size) fonctionne partout (local + Pyodide/web)
        # contrairement à SysFont qui dépend des polices système
        self.font = pygame.font.Font(None, 20)
        self.font_large = pygame.font.Font(None, 24)

        # Surface pour la zone de pénalité (semi-transparente)
        self._wall_zone_surface = self._build_wall_zone_surface()

    def _build_wall_zone_surface(self) -> pygame.Surface:
        """Pré-rend la zone de pénalité murale (gradient semi-transparent)."""
        surface = pygame.Surface((self.env_width, self.env_height), pygame.SRCALPHA)
        zw = int(self.zone_width)

        for i in range(zw):
            # Gradient : plus opaque près du mur
            alpha = int(40 * (1.0 - i / zw))
            color = (200, 40, 40, alpha)
            # Haut
            pygame.draw.line(surface, color, (0, i), (self.env_width, i))
            # Bas
            pygame.draw.line(surface, color, (0, self.env_height - 1 - i), (self.env_width, self.env_height - 1 - i))
            # Gauche
            pygame.draw.line(surface, color, (i, 0), (i, self.env_height))
            # Droite
            pygame.draw.line(surface, color, (self.env_width - 1 - i, 0), (self.env_width - 1 - i, self.env_height))

        return surface

    def render(self, sim: Simulation, ticks_per_frame: int = 1) -> None:
        """Rend une frame complète de la simulation."""
        self.screen.fill(Colors.BG)

        # ── Zone de pénalité ──
        self.screen.blit(self._wall_zone_surface, (0, 0))

        # ── Grille subtile ──
        grid_size = 50
        for x in range(0, self.env_width, grid_size):
            pygame.draw.line(self.screen, Colors.GRID, (x, 0), (x, self.env_height))
        for y in range(0, self.env_height, grid_size):
            pygame.draw.line(self.screen, Colors.GRID, (0, y), (self.env_width, y))

        # ── Pommes ──
        for apple in sim.env.apples:
            if apple.respawn_at_tick >= 0:
                continue  # pomme inactive
            ax, ay = int(apple.x), int(apple.y)
            pygame.draw.circle(self.screen, Colors.FOOD, (ax, ay), self.food_radius)
            pygame.draw.circle(self.screen, Colors.FOOD_INNER, (ax, ay), max(2, self.food_radius - 3))

        # ── Agents ──
        best = sim.best_agent
        # Surface semi-transparente pour les agents non-best
        ghost_surface = pygame.Surface(
            (self.env_width, self.env_height), pygame.SRCALPHA
        )

        for agent in sim.agents:
            if not agent.alive:
                continue
            ax, ay = int(agent.x), int(agent.y)
            is_best = (agent is best)

            if is_best:
                # ── Meilleur agent : raycasts visibles + corps plein ──
                for (rx, ry, kind) in agent.rays:
                    if kind == 0.5:
                        color = Colors.RAY_FOOD
                    elif kind == 1.0:
                        color = Colors.RAY_WALL
                    else:
                        color = Colors.RAY_NONE
                    pygame.draw.line(self.screen, color, (ax, ay), (int(rx), int(ry)), 1)

                body_color = (100, 255, 100) if not agent.is_dying() else (100, 180, 60)
                pygame.draw.circle(self.screen, body_color, (ax, ay), self.agent_radius)
                pygame.draw.circle(self.screen, (255, 255, 255), (ax, ay), self.agent_radius, 2)

                speed = (agent.vx ** 2 + agent.vy ** 2) ** 0.5
                if speed > 0.1:
                    dx = agent.vx / speed
                    dy = agent.vy / speed
                    end_x = ax + int(dx * (self.agent_radius + 7))
                    end_y = ay + int(dy * (self.agent_radius + 7))
                    pygame.draw.line(self.screen, (255, 255, 255), (ax, ay), (end_x, end_y), 2)
            else:
                # ── Agents normaux : semi-transparents, pas de raycasts ──
                if agent.is_dying():
                    body_color = (255, 100, 50, 80)
                else:
                    body_color = (255, 220, 50, 80)
                pygame.draw.circle(ghost_surface, body_color, (ax, ay), self.agent_radius)

        self.screen.blit(ghost_surface, (0, 0))

        # ── Panneau HUD ──
        self._render_hud(sim, ticks_per_frame)

        pygame.display.flip()

    def _render_hud(self, sim: Simulation, ticks_per_frame: int) -> None:
        """Rend le panneau d'information à droite de l'environnement."""
        panel_x = self.env_width
        panel_rect = pygame.Rect(panel_x, 0, self.panel_width, self.screen_height)
        pygame.draw.rect(self.screen, (20, 20, 28), panel_rect)
        pygame.draw.line(self.screen, (50, 50, 60), (panel_x, 0), (panel_x, self.screen_height), 2)

        x = panel_x + 12
        y = 15
        line_h = 22

        # Titre
        title = self.font_large.render("ALife Simulation", True, Colors.HUD_HL)
        self.screen.blit(title, (x, y))
        y += line_h * 2

        # Métriques
        lines = [
            f"Tick: {sim.current_tick}",
            f"Population: {len(sim.agents)}",
            f"Food: {sim.env.food_available}/{self.env_cfg.food_count}",
            f"Record pommes: {sim.record_apples}",
            f"Reproductions: {sim.total_reproductions}",
            f"Speed: {ticks_per_frame}x",
        ]

        if sim.agents:
            avg_energy = sum(a.energy for a in sim.agents) / len(sim.agents)
            avg_net = sum(a.network.network_size for a in sim.agents) / len(sim.agents)
            lines.append(f"Avg energy: {avg_energy:.2f}")
            lines.append(f"Avg net size: {avg_net:.0f}")

        for line in lines:
            text = self.font.render(line, True, Colors.HUD_FG)
            self.screen.blit(text, (x, y))
            y += line_h

        # Info meilleur agent
        if sim.best_agent and sim.best_agent.alive:
            y += line_h
            best = sim.best_agent
            header = self.font_large.render("Best Agent", True, (100, 255, 100))
            self.screen.blit(header, (x, y))
            y += line_h
            best_info = [
                f"Food eaten: {best.food_eaten}",
                f"Energy: {best.energy:.2f}",
                f"Age: {best.age}",
                f"Children: {best.children_count}",
                f"Net size: {best.network.network_size}",
            ]
            for info in best_info:
                text = self.font.render(info, True, (100, 255, 100))
                self.screen.blit(text, (x, y))
                y += line_h

        # Contrôles
        y += 20
        controls = [
            "[SPACE] Pause/Resume",
            "[UP/DOWN] Speed",
            "[R] Raycasts ON/OFF",
            "[ESC] Quitter",
        ]
        header = self.font_large.render("Controls", True, Colors.HUD_HL)
        self.screen.blit(header, (x, y))
        y += line_h
        for ctrl in controls:
            text = self.font.render(ctrl, True, (140, 140, 160))
            self.screen.blit(text, (x, y))
            y += line_h

    def handle_events(self) -> tuple[bool, int, bool]:
        """
        Gère les événements Pygame.
        Retourne (running, ticks_per_frame, show_raycasts).
        """
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False, 1, True
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False, 1, True
        return True, 1, True

    def tick_clock(self, target_fps: int) -> None:
        """Attend le prochain frame pour maintenir le FPS cible."""
        self.clock.tick(target_fps)

    def quit(self) -> None:
        """Nettoie Pygame."""
        pygame.quit()