"""Renderer: the only Pygame-aware module — wraps a headless ``Simulation``.

Phase 7 visualises Phases 1-6 without changing any of them (invariant n°7). The
renderer owns an internal :class:`Simulation` and reads it through its public
surface only (``sim.tick``, ``sim.population``, ``sim.env.apples``,
``sim.population_size``, ``sim.food_available``, ``sim.record_apples``,
``sim.tick_count``). It never recomputes simulation state.

Design notes:
- Window == world (overlay layout): simulation coordinates are screen coordinates,
  so no world->screen transform is needed. UI bars are painted semi-transparently
  over the world.
- Raycasts are reconstructed from the public ``Agent.last_senses`` cache (the
  perception the agent last acted on): ray angles come from the shared
  ``ray_angles`` helper and each endpoint is ``(x + d·max_dist·cosθ,
  y + d·max_dist·sinθ)`` where ``d`` is the normalised distance. No private
  agent geometry is touched and perception is never recomputed for display.
- Invariant n°1 (no magic simulation numbers) is respected: every *physics* value
  comes from ``SimConfig``. The literals below are presentation-only and named.

Playback speed (``ticks_per_frame``) is adjustable at runtime via keyboard and the
five on-screen buttons; the screen itself runs at ``config.render.fps``.
"""

from __future__ import annotations

import math

import pygame

from src.agent import ray_angles
from src.config import SimConfig
from src.simulation import Simulation

# --------------------------------------------------------------------------- #
# Presentation constants (named, not magic — see module docstring).
# --------------------------------------------------------------------------- #
COLOR_BACKGROUND = (18, 18, 24)
COLOR_APPLE = (220, 40, 40)
COLOR_ENERGY_LOW = (255, 0, 0)  # energy 0.0 -> red
COLOR_ENERGY_MID = (255, 255, 0)  # energy 0.5 -> yellow
COLOR_ENERGY_HIGH = (0, 255, 0)  # energy 1.0 -> green
COLOR_END_OF_LIFE = (255, 0, 0)  # agents fade toward this over their final ticks

COLOR_RAY_WALL = (0, 200, 220)  # cyan
COLOR_RAY_APPLE = (255, 165, 0)  # orange
COLOR_RAY_NOTHING = (160, 160, 160)  # light grey
RAY_ALPHA_HIT = 70  # non-selected agents: only rays that hit something
RAY_ALPHA_SELECTED_HIT = 200  # selected agent: hit rays
RAY_ALPHA_SELECTED_NOTHING = 35  # selected agent: nothing-rays (faint)
RAY_WIDTH = 1

COLOR_AGENT_SELECTED = (255, 255, 255)
AGENT_SELECTED_RING_WIDTH = 2
AGENT_SELECTED_EXTRA_R = 4


COLOR_PENALTY = (180, 40, 40)  # band tint along the walls
PENALTY_MAX_ALPHA = 90  # alpha at the wall, ramps to 0 inward
PENALTY_STEPS = 16  # number of nested rectangles approximating the gradient

COLOR_UI_BAR = (0, 0, 0)
UI_BAR_ALPHA = 150
COLOR_BTN = (60, 60, 70)
COLOR_BTN_ACTIVE = (90, 130, 90)
COLOR_BTN_BORDER = (200, 200, 200)
COLOR_TEXT = (235, 235, 235)

BAR_HEIGHT = 44
BAR_MARGIN = 8
BTN_W = 56
BTN_H = 28
BTN_GAP = 6
SPEED_TEXT_GAP = 16

HUD_MARGIN = 12
HUD_LINE_GAP = 4
FONT_PX = 20

SPEED_MIN = 1
SPEED_MAX = 32

# Button identifiers, left to right.
_BTN_FAST_DOWN = "<<"
_BTN_DOWN = "<"
_BTN_PLAY = "play"
_BTN_UP = ">"
_BTN_FAST_UP = ">>"
_BTN_GLYPHS = {
    _BTN_FAST_DOWN: "<<",
    _BTN_DOWN: "<",
    _BTN_PLAY: ">",  # replaced by pause glyph when running
    _BTN_UP: ">",
    _BTN_FAST_UP: ">>",
}
_BTN_ORDER = (_BTN_FAST_DOWN, _BTN_DOWN, _BTN_PLAY, _BTN_UP, _BTN_FAST_UP)


def _lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation between ``a`` and ``b`` for ``t`` in ``[0, 1]``."""
    return a + (b - a) * t


class Renderer:
    """Pygame visualisation wrapping an internal headless ``Simulation``."""

    def __init__(self, config: SimConfig) -> None:
        self._config = config

        pygame.init()  # pylint: disable=no-member
        pygame.font.init()

        width = config.render.window_width
        height = config.render.window_height
        self._screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("ALife Neuroevolution")
        self._clock = pygame.time.Clock()
        self._font = pygame.font.SysFont("monospace", FONT_PX)

        # Reusable per-frame translucent layer for rays, penalty band and bars.
        self._overlay = pygame.Surface(
            (width, height), pygame.SRCALPHA  # pylint: disable=no-member
        )

        self.sim = Simulation(config)
        self.ticks_per_frame = SPEED_MIN
        self.paused = False
        self._running = True
        self._selected_agent = None

        self._buttons: dict[str, pygame.Rect] = self._build_buttons()

    # ------------------------------------------------------------------ #
    # Setup helpers
    # ------------------------------------------------------------------ #
    def _build_buttons(self) -> dict[str, pygame.Rect]:
        """Lay out the five control buttons left-to-right in the top bar."""
        buttons: dict[str, pygame.Rect] = {}
        x = BAR_MARGIN
        y = (BAR_HEIGHT - BTN_H) // 2
        for name in _BTN_ORDER:
            buttons[name] = pygame.Rect(x, y, BTN_W, BTN_H)
            x += BTN_W + BTN_GAP
        return buttons

    # ------------------------------------------------------------------ #
    # Main loop
    # ------------------------------------------------------------------ #
    def run(self) -> None:
        """Drive the visual loop until the window is closed or ESC is pressed."""
        self.sim.open_csv_logger()
        try:
            while self._running:
                self._handle_events()
                if not self.paused and not self.sim.is_extinct:
                    for _ in range(self.ticks_per_frame):
                        self.sim.tick()
                self._draw()
                self._clock.tick(self._config.render.fps)
        finally:
            self.sim.close_csv_logger()
            pygame.quit()  # pylint: disable=no-member

    # ------------------------------------------------------------------ #
    # Input
    # ------------------------------------------------------------------ #
    def _handle_events(self) -> None:
        """Process keyboard, mouse and window events for one frame."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:  # pylint: disable=no-member
                self._running = False
            elif event.type == pygame.KEYDOWN:  # pylint: disable=no-member
                self._handle_key(event.key)
            elif event.type == pygame.MOUSEBUTTONDOWN:  # pylint: disable=no-member
                if event.button == 1:
                    self._handle_click(event.pos)

    def _handle_key(self, key: int) -> None:
        """Route a single key-down to its action."""
        if key == pygame.K_ESCAPE:  # pylint: disable=no-member
            self._running = False
        elif key == pygame.K_SPACE:  # pylint: disable=no-member
            self.paused = not self.paused
        elif key in (
            pygame.K_PLUS,  # pylint: disable=no-member
            pygame.K_EQUALS,  # pylint: disable=no-member
            pygame.K_KP_PLUS,  # pylint: disable=no-member
        ):
            self._speed_up()
        elif key in (
            pygame.K_MINUS,  # pylint: disable=no-member
            pygame.K_KP_MINUS,  # pylint: disable=no-member
        ):
            self._speed_down()

    def _handle_click(self, pos: tuple[int, int]) -> None:
        """Dispatch a left click to a control button or select/deselect an agent."""
        for name, rect in self._buttons.items():
            if rect.collidepoint(pos):
                if name in (_BTN_FAST_DOWN, _BTN_DOWN):
                    self._speed_down()
                elif name in (_BTN_UP, _BTN_FAST_UP):
                    self._speed_up()
                else:  # play/pause
                    self.paused = not self.paused
                return
        # No button hit: select the nearest agent whose circle contains the click.
        r = self._config.agent.radius
        px, py = pos
        for agent in self.sim.population:
            dx, dy = agent.x - px, agent.y - py
            if dx * dx + dy * dy <= r * r:
                self._selected_agent = None if agent is self._selected_agent else agent
                return
        self._selected_agent = None

    def _speed_up(self) -> None:
        """Double the ticks-per-frame, capped at ``SPEED_MAX``."""
        self.ticks_per_frame = min(SPEED_MAX, self.ticks_per_frame * 2)

    def _speed_down(self) -> None:
        """Halve the ticks-per-frame, floored at ``SPEED_MIN``."""
        self.ticks_per_frame = max(SPEED_MIN, self.ticks_per_frame // 2)

    # ------------------------------------------------------------------ #
    # Drawing
    # ------------------------------------------------------------------ #
    def _draw(self) -> None:
        """Render one full frame: world, agents, UI, then present it."""
        self._screen.fill(COLOR_BACKGROUND)
        self._overlay.fill((0, 0, 0, 0))

        self._draw_penalty_zone()
        self._draw_raycasts()
        self._draw_apples()
        self._draw_agents()
        self._draw_ui()
        self._draw_hud()

        self._screen.blit(self._overlay, (0, 0))
        pygame.display.flip()

    def _draw_penalty_zone(self) -> None:
        """Approximate the wall penalty gradient with nested translucent frames."""
        width = self._config.render.window_width
        height = self._config.render.window_height
        zone = self._config.penalty_zone.width
        step = zone / PENALTY_STEPS
        for i in range(PENALTY_STEPS):
            inset = i * step
            # Alpha highest at the wall (i == 0), fading inward (mirrors penalty_at).
            alpha = int(PENALTY_MAX_ALPHA * (1.0 - i / PENALTY_STEPS))
            color = (*COLOR_PENALTY, alpha)
            rect = pygame.Rect(
                inset,
                inset,
                width - 2 * inset,
                height - 2 * inset,
            )
            pygame.draw.rect(self._overlay, color, rect, width=max(1, math.ceil(step)))

    def _draw_raycasts(self) -> None:
        """Draw rays from each agent's cached ``last_senses``.

        Non-selected agents: only rays that hit something (apple or wall) are
        drawn — nothing-rays are the majority and add visual noise without
        information. The selected agent (if any) shows all 16 rays, with
        hit-rays bright and nothing-rays faint. Selection is reset automatically
        when the selected agent dies. Angles are computed per-agent because each
        agent has its own heading (egocentric raycasts).
        """
        if self._selected_agent not in self.sim.population:
            self._selected_agent = None

        num_rays = self._config.sensors.num_rays
        fov = self._config.sensors.fov
        for agent in self.sim.population:
            angles = ray_angles(num_rays, fov, agent.heading)
            self._draw_agent_rays(agent, angles, agent is self._selected_agent)

    def _draw_agent_rays(self, agent, angles: list[float], is_selected: bool) -> None:
        """Draw one agent's rays onto the overlay (49-input encoding)."""
        n = len(angles)
        max_dist = self._config.sensors.max_distance
        senses = agent.last_senses or agent.sense()
        ax, ay = agent.x, agent.y
        for i, angle in enumerate(angles):
            apple_flag = senses[n + i]  # [16..31]
            wall_flag = senses[2 * n + i]  # [32..47]
            is_nothing = apple_flag == 0.0 and wall_flag == 0.0
            if not is_selected and is_nothing:
                continue
            d = senses[i] * max_dist
            pygame.draw.line(
                self._overlay,
                (
                    *self._ray_color(apple_flag, wall_flag),
                    self._ray_alpha(is_selected, is_nothing),
                ),
                (ax, ay),
                (ax + d * math.cos(angle), ay + d * math.sin(angle)),
                RAY_WIDTH,
            )

    @staticmethod
    def _ray_alpha(is_selected: bool, is_nothing: bool) -> int:
        """Return the alpha for one ray line depending on selection state."""
        if not is_selected:
            return RAY_ALPHA_HIT
        return RAY_ALPHA_SELECTED_NOTHING if is_nothing else RAY_ALPHA_SELECTED_HIT

    @staticmethod
    def _ray_color(apple_flag: float, wall_flag: float) -> tuple[int, int, int]:
        """Map apple/wall presence flags to a line colour."""
        if apple_flag == 1.0:
            return COLOR_RAY_APPLE
        if wall_flag == 1.0:
            return COLOR_RAY_WALL
        return COLOR_RAY_NOTHING

    def _draw_apples(self) -> None:
        """Draw live apples as opaque red circles (pending apples are excluded)."""
        radius = int(self._config.apple.radius)
        for apple in self.sim.env.apples:
            pygame.draw.circle(
                self._screen, COLOR_APPLE, (int(apple.x), int(apple.y)), radius
            )

    def _draw_agents(self) -> None:
        """Draw each living agent as a circle tinted by its energy/age state."""
        radius = int(self._config.agent.radius)
        for agent in self.sim.population:
            color = self._agent_color(agent)
            pygame.draw.circle(
                self._screen, color, (int(agent.x), int(agent.y)), radius
            )
            if agent is self._selected_agent:
                pygame.draw.circle(
                    self._screen,
                    COLOR_AGENT_SELECTED,
                    (int(agent.x), int(agent.y)),
                    radius + AGENT_SELECTED_EXTRA_R,
                    AGENT_SELECTED_RING_WIDTH,
                )

    def _agent_color(self, agent) -> tuple[int, int, int]:
        """Energy colour, blended toward red over the agent's final ticks.

        For most of life the colour is the plain energy ramp. Once the agent
        enters its last ``agent.end_of_life_ticks`` ticks (config-driven, no
        magic numbers), the energy colour is linearly interpolated toward
        ``COLOR_END_OF_LIFE`` as it approaches ``agent.max_age``.
        """
        base = self._energy_color(agent.energy)
        max_age = self._config.agent.max_age
        eol = self._config.agent.end_of_life_ticks
        start = max_age - eol
        if agent.age < start:
            return base
        ratio = max(0.0, min(1.0, (agent.age - start) / eol))
        return (
            int(_lerp(base[0], COLOR_END_OF_LIFE[0], ratio)),
            int(_lerp(base[1], COLOR_END_OF_LIFE[1], ratio)),
            int(_lerp(base[2], COLOR_END_OF_LIFE[2], ratio)),
        )

    def _energy_color(self, energy: float) -> tuple[int, int, int]:
        """Smooth red->yellow->green ramp over normalised energy ``[0, 1]``."""
        t = max(0.0, min(1.0, energy / self._config.agent.max_energy))
        if t <= 0.5:
            u = t / 0.5
            low, high = COLOR_ENERGY_LOW, COLOR_ENERGY_MID
        else:
            u = (t - 0.5) / 0.5
            low, high = COLOR_ENERGY_MID, COLOR_ENERGY_HIGH
        return (
            int(_lerp(low[0], high[0], u)),
            int(_lerp(low[1], high[1], u)),
            int(_lerp(low[2], high[2], u)),
        )

    # ------------------------------------------------------------------ #
    # UI overlay
    # ------------------------------------------------------------------ #
    def _draw_ui(self) -> None:
        """Draw the top control bar: five buttons plus the live speed readout."""
        width = self._config.render.window_width
        bar_rect = pygame.Rect(0, 0, width, BAR_HEIGHT)
        pygame.draw.rect(self._overlay, (*COLOR_UI_BAR, UI_BAR_ALPHA), bar_rect)

        for name in _BTN_ORDER:
            rect = self._buttons[name]
            active = name == _BTN_PLAY and self.paused
            pygame.draw.rect(
                self._screen, COLOR_BTN_ACTIVE if active else COLOR_BTN, rect
            )
            pygame.draw.rect(self._screen, COLOR_BTN_BORDER, rect, width=1)
            glyph = "||" if name == _BTN_PLAY and not self.paused else _BTN_GLYPHS[name]
            self._blit_centered(glyph, rect)

        last = self._buttons[_BTN_FAST_UP]
        speed_label = self._font.render(
            f"Speed: {self.ticks_per_frame}x", True, COLOR_TEXT
        )
        self._screen.blit(
            speed_label,
            (last.right + SPEED_TEXT_GAP, (BAR_HEIGHT - speed_label.get_height()) // 2),
        )

    def _blit_centered(self, text: str, rect: pygame.Rect) -> None:
        """Render ``text`` centred inside ``rect`` on the screen surface."""
        label = self._font.render(text, True, COLOR_TEXT)
        self._screen.blit(label, label.get_rect(center=rect.center))

    def _draw_hud(self) -> None:
        """Draw the two bottom-left status lines."""
        line1 = (
            f"Population: {self.sim.population_size}/"
            f"{self._config.population.initial_size} | "
            f"Food: {self.sim.food_available}/{self._config.apple.count} active"
        )
        line2 = (
            f"Best fitness: {self.sim.record_apples} | "
            f"Tick: {self.sim.tick_count} | Speed: {self.ticks_per_frame}x"
        )
        surf1 = self._font.render(line1, True, COLOR_TEXT)
        surf2 = self._font.render(line2, True, COLOR_TEXT)
        height = self._config.render.window_height
        y2 = height - HUD_MARGIN - surf2.get_height()
        y1 = y2 - HUD_LINE_GAP - surf1.get_height()
        self._screen.blit(surf1, (HUD_MARGIN, y1))
        self._screen.blit(surf2, (HUD_MARGIN, y2))
