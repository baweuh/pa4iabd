import math
import random
import sys

import pygame

from genetic_network import GeneticNetwork
from population import Population

# ---------------------------------------------------------------------------
# CONSTANTS  — tweak these freely
# ---------------------------------------------------------------------------
SCREEN_WIDTH = 1000
SCREEN_HEIGHT = 700
FPS = 60

POPULATION_SIZE = 100
FOOD_COUNT = 10  # suggested number shown in placement screen hint
INDIVIDUAL_SPEED = 2.5  # pixels per tick
GENERATION_DURATION = 30.0  # max seconds per generation
NO_FOOD_TIMEOUT = 30.0  # seconds without any food eaten → end generation

# NN shape
VISIBLE_FOOD = 10  # how many nearest food items each individual can sense
#   inputs = VISIBLE_FOOD*2 (dx,dy each) + 2 (velocity) + 4 (walls) = 12
INPUT_SIZE = VISIBLE_FOOD * 2 + 2 + 4
HIDDEN_SIZES = [16, 8]  # one entry per hidden layer, e.g. [16, 8] = two hidden layers
OUTPUT_SIZE = 2

MUTATION_RATE = 0.05
ELITE_COUNT = 25  # top N networks copied unchanged each generation

# Coverage grid — rewards exploring new areas
COVERAGE_COLS = 20  # grid columns
COVERAGE_ROWS = 14  # grid rows  (≈ same cell size as cols given 1000×700)
COVERAGE_REWARD = 0.5  # fitness per new cell visited (max ~2.8, less than one food)
COVERAGE_COLOR = (60, 120, 200, 35)  # RGBA tint for visited cells on best individual
WALL_PENALTY_DIST = 100  # pixels from wall that triggers penalty
WALL_PENALTY = 3  # fitness deducted per tick per wall being hugged
WALL_ZONE_COLOR = (200, 40, 40, 30)  # RGBA tint for penalty zone overlay

# Speed chain reward — bonuses for eating food quickly in succession
SPEED_BONUS_BASE = 5.0  # bonus fitness at exactly 1s between foods (scales as base/dt)
SPEED_BONUS_MAX = 20.0  # cap per eat so near-simultaneous eats don't explode
CHAIN_THRESHOLD = 3.0  # seconds — eat within this to keep the chain alive
CHAIN_MAX = 5  # maximum chain multiplier

# Adaptive mutation
STAGNATION_LIMIT = 5  # generations without improvement before boosting mutation
MUTATION_BOOST = 1.2  # multiplier applied to mutation rate when stagnating
MUTATION_MAX = 0.95  # hard cap so it never goes fully random

# Fast-forward: how many simulation ticks run per rendered frame
FAST_TICKS_PER_FRAME = 30

# ---------------------------------------------------------------------------
# COLOURS
# ---------------------------------------------------------------------------
BG_COLOR = (15, 15, 20)
INDIVIDUAL_COLOR = (255, 220, 50)
INDIVIDUAL_BEST_CLR = (255, 140, 0)  # highlight the current best
INDIVIDUAL_ELITE_CLR = (80, 220, 255)  # carried-over elite individuals
GHOST_ALPHA = 55  # opacity for non-best individuals (0-255)
FOOD_COLOR = (220, 50, 50)
HUD_COLOR = (200, 200, 200)
HUD_ACCENT = (255, 220, 50)
FAST_BADGE_COLOR = (50, 200, 120)
SLOW_BADGE_COLOR = (100, 140, 255)
GRID_COLOR = (25, 25, 32)
GRAPH_BEST_COLOR = (255, 220, 50)  # best fitness line on graph
GRAPH_AVG_COLOR = (140, 140, 140)  # average fitness line on graph
GRAPH_BG = (0, 0, 0, 180)
REPLAY_BADGE_COLOR = (255, 80, 200)  # replay mode banner
PLACEMENT_COLOR = (255, 220, 50)  # food ghost / placed dot in placement phase
PLACEMENT_BG = (0, 0, 0, 200)

# Sizes
INDIVIDUAL_SIZE = 10  # half-side of the square
FOOD_RADIUS = 7
EAT_RADIUS = INDIVIDUAL_SIZE + FOOD_RADIUS  # collision distance

# Fitness graph panel (bottom-right)
GRAPH_W = 260
GRAPH_H = 120
GRAPH_MAX_POINTS = 80  # how many generations to show before scrolling


# ---------------------------------------------------------------------------
# Individual — wraps a GeneticNetwork with position / velocity state
# ---------------------------------------------------------------------------
class Individual:
    def __init__(self, network: GeneticNetwork, is_elite: bool = False):
        self.network = network
        self.is_elite = is_elite
        self.x = SCREEN_WIDTH / 2.0
        self.y = SCREEN_HEIGHT / 2.0
        self.vx = 0.0
        self.vy = 0.0
        self.food: list[list[float]] = []  # private food copy
        self.last_eat_t = 0.0  # time of last food eaten this individual
        self.done = False  # True when this individual's run is over
        self.visited: set[tuple[int, int]] = set()  # grid cells visited this generation
        self.peak_fitness = 0.0  # highest fitness reached this generation
        self.chain_mult = 1  # current chain multiplier (resets if too slow)

    # ------------------------------------------------------------------
    def update(self, food_list: list[tuple[float, float]]):
        """Run one NN tick and move."""
        if not food_list:
            return

        # --- Multi-food inputs (VISIBLE_FOOD nearest, padded with zeros if fewer exist) ---
        sorted_food = sorted(
            food_list, key=lambda f: (f[0] - self.x) ** 2 + (f[1] - self.y) ** 2
        )
        food_inputs: list[float] = []
        for i in range(VISIBLE_FOOD):
            if i < len(sorted_food):
                fx, fy = sorted_food[i]
                dx = fx - self.x
                dy = fy - self.y
                food_inputs += [
                    max(-1.0, min(1.0, dx / SCREEN_WIDTH)),
                    max(-1.0, min(1.0, dy / SCREEN_HEIGHT)),
                ]
            else:
                food_inputs += [0.0, 0.0]  # padded: no food

        # --- Wall proximity inputs (normalised 0→1, 0 = touching wall) ---
        wall_inputs = [
            self.x / SCREEN_WIDTH,  # dist to left wall
            (SCREEN_WIDTH - self.x) / SCREEN_WIDTH,  # dist to right wall
            self.y / SCREEN_HEIGHT,  # dist to top wall
            (SCREEN_HEIGHT - self.y) / SCREEN_HEIGHT,  # dist to bottom wall
        ]

        # --- Velocity ---
        vel_inputs = [self.vx, self.vy]

        inputs = food_inputs + vel_inputs + wall_inputs  # length = INPUT_SIZE

        outputs = self.network.predict(inputs)  # [move_x, move_y]
        raw_x, raw_y = outputs[0], outputs[1]

        # Normalise NN output to unit vector then scale by speed
        mag = math.hypot(raw_x, raw_y) or 1.0
        self.vx = raw_x / mag
        self.vy = raw_y / mag

        self.x += self.vx * INDIVIDUAL_SPEED
        self.y += self.vy * INDIVIDUAL_SPEED

        # Bounce off walls
        if self.x < INDIVIDUAL_SIZE:
            self.x = INDIVIDUAL_SIZE
            self.vx *= -1
        if self.x > SCREEN_WIDTH - INDIVIDUAL_SIZE:
            self.x = SCREEN_WIDTH - INDIVIDUAL_SIZE
            self.vx *= -1
        if self.y < INDIVIDUAL_SIZE:
            self.y = INDIVIDUAL_SIZE
            self.vy *= -1
        if self.y > SCREEN_HEIGHT - INDIVIDUAL_SIZE:
            self.y = SCREEN_HEIGHT - INDIVIDUAL_SIZE
            self.vy *= -1

    # ------------------------------------------------------------------
    def _nearest_food(self, food_list):
        return min(food_list, key=lambda f: (f[0] - self.x) ** 2 + (f[1] - self.y) ** 2)

    # ------------------------------------------------------------------
    def draw(self, surface: pygame.Surface, is_best: bool = False, alpha: int = 255):
        if is_best:
            color = INDIVIDUAL_BEST_CLR
        elif self.is_elite:
            color = INDIVIDUAL_ELITE_CLR
        else:
            color = INDIVIDUAL_COLOR

        if alpha < 255:
            # Draw onto a temporary surface then blit with alpha
            tmp = pygame.Surface(
                (INDIVIDUAL_SIZE * 2, INDIVIDUAL_SIZE * 2), pygame.SRCALPHA
            )
            tmp.fill((*color, alpha))
            surface.blit(
                tmp, (int(self.x) - INDIVIDUAL_SIZE, int(self.y) - INDIVIDUAL_SIZE)
            )
        else:
            rect = pygame.Rect(
                int(self.x) - INDIVIDUAL_SIZE,
                int(self.y) - INDIVIDUAL_SIZE,
                INDIVIDUAL_SIZE * 2,
                INDIVIDUAL_SIZE * 2,
            )
            pygame.draw.rect(surface, color, rect)
            if is_best:
                pygame.draw.rect(surface, (255, 255, 255), rect, 2)


# ---------------------------------------------------------------------------
# Simulation state
# ---------------------------------------------------------------------------
class Simulation:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Neuroevolution — Food Foraging")
        self.clock = pygame.time.Clock()
        self.font_lg = pygame.font.SysFont("monospace", 22, bold=True)
        self.font_sm = pygame.font.SysFont("monospace", 16)

        # --- Placement phase: let user set fixed food positions ---
        self.food_positions: list[tuple[float, float]] = []
        self._run_placement()  # blocks until user presses Enter

        # --- GA setup ---
        self.population = Population(POPULATION_SIZE)
        self.population.set_mutation_rate(MUTATION_RATE)
        self.population.init_population(INPUT_SIZE, HIDDEN_SIZES, OUTPUT_SIZE)

        self.individuals: list[Individual] = [
            Individual(net) for net in self.population.pop
        ]

        # Stats
        self.generation = 0
        self.best_fitness_ever = 0.0
        self.best_fitness_gen = 0.0
        self.all_time_best: GeneticNetwork | None = None
        self.best_of_last_gen: GeneticNetwork | None = None

        # Adaptive mutation tracking
        self.current_mutation_rate = MUTATION_RATE
        self.stagnation_counter = 0
        self.is_stagnating = False

        # Fitness history for graph — list of (best, avg) per generation
        self.fitness_history: list[tuple[float, float]] = []

        # Replay state
        self.replay_mode = False
        self.replay_individual: Individual | None = None
        self.replay_food: list[list[float]] = []
        self.replay_time = 0.0
        self.replay_last_eat = 0.0
        # Snapshot of paused evolution state (populated by _enter_replay)
        self._paused_gen_time = 0.0
        self._paused_ind_state = []

        # Speed toggle
        self.fast_forward = False

        self._start_generation()

    # ------------------------------------------------------------------
    def _run_placement(self):
        """Blocking placement phase — user clicks to place food, Enter to confirm."""
        pygame.display.set_caption(
            "Place food — Left-click to add, Right-click to remove, Enter to start"
        )

        MIN_FOOD = 1
        snap_r = FOOD_RADIUS + 4  # snap/remove radius

        while True:
            self.clock.tick(FPS)
            mx, my = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

                if event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:  # left — place
                        # Avoid placing too close to an existing dot
                        too_close = any(
                            math.hypot(mx - fx, my - fy) < snap_r * 2
                            for fx, fy in self.food_positions
                        )
                        if not too_close:
                            self.food_positions.append((float(mx), float(my)))

                    elif event.button == 3:  # right — remove nearest
                        if self.food_positions:
                            nearest = min(
                                self.food_positions,
                                key=lambda f: math.hypot(mx - f[0], my - f[1]),
                            )
                            if (
                                math.hypot(mx - nearest[0], my - nearest[1])
                                < snap_r * 4
                            ):
                                self.food_positions.remove(nearest)

                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        if len(self.food_positions) >= MIN_FOOD:
                            self._run_spawn_placement()
                            pygame.display.set_caption("Neuroevolution — Food Foraging")
                            return
                    if event.key == pygame.K_ESCAPE:
                        pygame.quit()
                        sys.exit()

            # ---- Draw placement screen ----
            self.screen.fill(BG_COLOR)

            # Grid
            for gx in range(0, SCREEN_WIDTH, 80):
                pygame.draw.line(self.screen, GRID_COLOR, (gx, 0), (gx, SCREEN_HEIGHT))
            for gy in range(0, SCREEN_HEIGHT, 80):
                pygame.draw.line(self.screen, GRID_COLOR, (0, gy), (SCREEN_WIDTH, gy))

            # Placed food dots
            for fx, fy in self.food_positions:
                pygame.draw.circle(
                    self.screen, FOOD_COLOR, (int(fx), int(fy)), FOOD_RADIUS
                )
                pygame.draw.circle(
                    self.screen, (255, 120, 120), (int(fx), int(fy)), FOOD_RADIUS - 2
                )

            # Ghost dot following cursor
            pygame.draw.circle(
                self.screen, (*FOOD_COLOR, 120), (mx, my), FOOD_RADIUS, 2
            )

            # Instructions panel
            can_start = len(self.food_positions) >= MIN_FOOD
            instructions = [
                "PLACE FOOD",
                "",
                "Left-click   — place food",
                "Right-click  — remove nearest",
                f"Enter        — start  {'✓' if can_start else f'(place at least {MIN_FOOD})'}",
                "Escape       — quit",
                "",
                f"Placed: {len(self.food_positions)}   (suggested: {FOOD_COUNT})",
            ]
            panel_w = 310
            panel_h = len(instructions) * 26 + 20
            panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
            panel.fill((0, 0, 0, 200))
            self.screen.blit(panel, (8, 8))

            y = 16
            for line in instructions:
                if line == "PLACE FOOD":
                    surf = self.font_lg.render(line, True, HUD_ACCENT)
                elif line == "":
                    y += 4
                    continue
                elif line.startswith("Placed:"):
                    color = (80, 220, 120) if can_start else (220, 100, 80)
                    surf = self.font_sm.render(line, True, color)
                else:
                    surf = self.font_sm.render(line, True, HUD_COLOR)
                self.screen.blit(surf, (16, y))
                y += 26

            pygame.display.flip()

    # ------------------------------------------------------------------
    def _run_spawn_placement(self):
        """Second placement phase — one click sets the fixed spawn point."""
        self.spawn_point: tuple[float, float] = (SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2)
        confirmed = False

        while not confirmed:
            self.clock.tick(FPS)
            mx, my = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.spawn_point = (float(mx), float(my))
                    confirmed = True
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    sys.exit()

            # ---- Draw spawn placement screen ----
            self.screen.fill(BG_COLOR)

            # Grid
            for gx in range(0, SCREEN_WIDTH, 80):
                pygame.draw.line(self.screen, GRID_COLOR, (gx, 0), (gx, SCREEN_HEIGHT))
            for gy in range(0, SCREEN_HEIGHT, 80):
                pygame.draw.line(self.screen, GRID_COLOR, (0, gy), (SCREEN_WIDTH, gy))

            # Fixed food dots (already placed)
            for fx, fy in self.food_positions:
                pygame.draw.circle(
                    self.screen, FOOD_COLOR, (int(fx), int(fy)), FOOD_RADIUS
                )
                pygame.draw.circle(
                    self.screen, (255, 120, 120), (int(fx), int(fy)), FOOD_RADIUS - 2
                )

            # Ghost spawn square following cursor
            ghost_rect = pygame.Rect(
                mx - INDIVIDUAL_SIZE,
                my - INDIVIDUAL_SIZE,
                INDIVIDUAL_SIZE * 2,
                INDIVIDUAL_SIZE * 2,
            )
            pygame.draw.rect(self.screen, (*INDIVIDUAL_COLOR, 160), ghost_rect, 2)

            # Instructions panel
            instructions = [
                "SET SPAWN POINT",
                "",
                "Left-click   — place spawn",
                "Escape       — quit",
                "",
                "All individuals will spawn",
                "here every generation.",
            ]
            panel_w = 310
            panel_h = len(instructions) * 26 + 20
            panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
            panel.fill((0, 0, 0, 200))
            self.screen.blit(panel, (8, 8))

            y = 16
            for line in instructions:
                if line == "SET SPAWN POINT":
                    surf = self.font_lg.render(line, True, INDIVIDUAL_COLOR)
                elif line == "":
                    y += 4
                    continue
                else:
                    surf = self.font_sm.render(line, True, HUD_COLOR)
                self.screen.blit(surf, (16, y))
                y += 26

            pygame.display.flip()

    # ------------------------------------------------------------------
    def _start_generation(self):
        """Reset positions, give each individual a private food copy, reset timers."""
        self.gen_time = 0.0
        self.best_fitness_gen = 0.0

        sx, sy = self.spawn_point
        for ind in self.individuals:
            ind.x = sx
            ind.y = sy
            ind.vx = 0.0
            ind.vy = 0.0
            ind.network.fitness = 0.0
            ind.food = [[fx, fy] for fx, fy in self.food_positions]
            ind.last_eat_t = 0.0
            ind.done = False
            ind.visited = set()
            ind.peak_fitness = 0.0
            ind.chain_mult = 1

    # ------------------------------------------------------------------
    def _tick(self, dt: float):
        """Advance simulation by one logical step — each individual evaluated solo."""
        self.gen_time += dt

        for ind in self.individuals:
            if ind.done:
                continue

            ind.update(ind.food)

            # Coverage reward — one-time bonus per new grid cell visited
            cell = (
                int(ind.x / SCREEN_WIDTH * COVERAGE_COLS),
                int(ind.y / SCREEN_HEIGHT * COVERAGE_ROWS),
            )
            if cell not in ind.visited:
                ind.visited.add(cell)
                ind.network.fitness += COVERAGE_REWARD

            # Wall penalty
            if ind.x < WALL_PENALTY_DIST:
                ind.network.fitness -= WALL_PENALTY
            if ind.x > SCREEN_WIDTH - WALL_PENALTY_DIST:
                ind.network.fitness -= WALL_PENALTY
            if ind.y < WALL_PENALTY_DIST:
                ind.network.fitness -= WALL_PENALTY
            if ind.y > SCREEN_HEIGHT - WALL_PENALTY_DIST:
                ind.network.fitness -= WALL_PENALTY

            # Check collisions against this individual's own food
            for food in ind.food:
                if math.hypot(ind.x - food[0], ind.y - food[1]) < EAT_RADIUS:
                    dt = max(0.05, self.gen_time - ind.last_eat_t)  # floor to avoid /0
                    speed_bonus = min(SPEED_BONUS_MAX, SPEED_BONUS_BASE / dt)
                    eat_reward = 10.0 + speed_bonus * ind.chain_mult

                    ind.network.fitness += eat_reward**1.2
                    food[0] = -9999.0
                    ind.last_eat_t = self.gen_time

                    # Chain: update multiplier based on how fast this eat was
                    if dt <= CHAIN_THRESHOLD:
                        ind.chain_mult = min(CHAIN_MAX, ind.chain_mult + 1)
                    else:
                        ind.chain_mult = 1

            ind.food = [f for f in ind.food if f[0] > -9000]

            # Update peak — captures best score before any future wall penalties
            if ind.network.fitness > ind.peak_fitness:
                ind.peak_fitness = ind.network.fitness

            # Mark done if all food eaten or personal timeout exceeded
            time_since_eat = self.gen_time - ind.last_eat_t
            if not ind.food or (
                self.gen_time > 1.0 and time_since_eat >= NO_FOOD_TIMEOUT
            ):
                ind.done = True

        self.best_fitness_gen = max(ind.peak_fitness for ind in self.individuals)

    # ------------------------------------------------------------------
    def _generation_should_end(self) -> bool:
        if self.gen_time >= GENERATION_DURATION:
            return True
        return all(ind.done for ind in self.individuals)

    # ------------------------------------------------------------------
    def _evolve(self):
        """Breed next generation using existing Population machinery."""

        # Commit peak fitness to network.fitness so selection uses it
        for ind in self.individuals:
            ind.network.fitness = ind.peak_fitness

        # Track all-time best and store last-gen best for replay
        gen_best = max(self.individuals, key=lambda i: i.peak_fitness)
        self.best_of_last_gen = gen_best.network
        if gen_best.peak_fitness > self.best_fitness_ever:
            self.best_fitness_ever = gen_best.peak_fitness
            self.all_time_best = gen_best.network
            self.stagnation_counter = 0
            self.is_stagnating = False
            self.current_mutation_rate = MUTATION_RATE
        else:
            self.stagnation_counter += 1
            if self.stagnation_counter >= STAGNATION_LIMIT:
                self.is_stagnating = True
                self.current_mutation_rate = min(
                    MUTATION_MAX, self.current_mutation_rate * MUTATION_BOOST
                )
                self.stagnation_counter = 0

        self.population.set_mutation_rate(self.current_mutation_rate)

        # Sort by fitness — used for both elitism and top-half selection
        sorted_pop = sorted(self.population.pop, key=lambda n: n.fitness, reverse=True)

        # Elitism — carry top ELITE_COUNT networks forward unchanged
        next_nets: list[GeneticNetwork] = sorted_pop[:ELITE_COUNT]

        # Restrict selection to the top half only
        top_half = sorted_pop[: max(2, POPULATION_SIZE // 2)]
        self.population.pop = top_half

        # Fill the rest via selection + crossover from top half
        for _ in range(POPULATION_SIZE - ELITE_COUNT):
            p1 = self.population.select()
            p2 = self.population.select()
            child = self.population.crossover(p1, p2)
            next_nets.append(child)

        # Replace population
        self.population.pop = next_nets
        self.population.generation += 1
        self.generation += 1

        # Record history for graph (using peak fitnesses)
        peaks = [ind.peak_fitness for ind in self.individuals]
        avg = sum(peaks) / len(peaks) if peaks else 0.0
        self.fitness_history.append((self.best_fitness_gen, avg))

        # Wrap new networks in fresh Individual objects (first ELITE_COUNT are elites)
        self.individuals = [
            Individual(net, is_elite=(i < ELITE_COUNT))
            for i, net in enumerate(self.population.pop)
        ]

    # ------------------------------------------------------------------
    def _enter_replay(self):
        """Pause evolution and showcase the best individual from the previous generation."""
        if self.best_of_last_gen is None:
            return
        # Snapshot per-individual state so we can resume exactly
        self._paused_gen_time = self.gen_time
        self._paused_ind_state = [
            (
                [f[:] for f in ind.food],
                ind.last_eat_t,
                ind.done,
                ind.network.fitness,
                ind.x,
                ind.y,
                ind.vx,
                ind.vy,
                set(ind.visited),
                ind.peak_fitness,
                ind.chain_mult,
            )
            for ind in self.individuals
        ]
        # Set up replay
        self.replay_mode = True
        self.replay_individual = Individual(self.best_of_last_gen)
        self.replay_food = [[fx, fy] for fx, fy in self.food_positions]
        self.replay_time = 0.0
        self.replay_last_eat = 0.0

    # ------------------------------------------------------------------
    def _exit_replay(self):
        """Return to evolution exactly where we left off."""
        self.replay_mode = False
        self.gen_time = self._paused_gen_time
        for ind, state in zip(self.individuals, self._paused_ind_state):
            food, last_eat, done, fitness, x, y, vx, vy, visited, peak, chain = state
            ind.food = [f[:] for f in food]
            ind.last_eat_t = last_eat
            ind.done = done
            ind.network.fitness = fitness
            ind.x, ind.y = x, y
            ind.vx, ind.vy = vx, vy
            ind.visited = set(visited)
            ind.peak_fitness = peak
            ind.chain_mult = chain

    # ------------------------------------------------------------------
    def _tick_replay(self, dt: float):
        """Advance the replay simulation by one tick."""
        self.replay_time += dt
        ind = self.replay_individual
        food = self.replay_food

        ind.update(food)

        # Eat food
        for f in food:
            if math.hypot(ind.x - f[0], ind.y - f[1]) < EAT_RADIUS:
                ind.network.fitness += 10.0
                f[0] = -9999.0
                self.replay_last_eat = self.replay_time

        self.replay_food = [f for f in food if f[0] > -9000]

        # End replay if all food eaten or timed out
        no_food_timeout = (
            self.replay_time > 1.0
            and (self.replay_time - self.replay_last_eat) >= NO_FOOD_TIMEOUT
        )
        if (
            not self.replay_food
            or self.replay_time >= GENERATION_DURATION
            or no_food_timeout
        ):
            # Loop: reset to fixed positions and fresh individual
            self.replay_individual = Individual(self.all_time_best)
            self.replay_food = [[fx, fy] for fx, fy in self.food_positions]
            self.replay_time = 0.0
            self.replay_last_eat = 0.0

    # ------------------------------------------------------------------
    def _draw(self):
        self.screen.fill(BG_COLOR)

        # Subtle grid
        for gx in range(0, SCREEN_WIDTH, 80):
            pygame.draw.line(self.screen, GRID_COLOR, (gx, 0), (gx, SCREEN_HEIGHT))
        for gy in range(0, SCREEN_HEIGHT, 80):
            pygame.draw.line(self.screen, GRID_COLOR, (0, gy), (SCREEN_WIDTH, gy))

        # Wall penalty zone overlay — four border rects at low opacity
        d = WALL_PENALTY_DIST
        zone_surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        pygame.draw.rect(zone_surf, WALL_ZONE_COLOR, (0, 0, d, SCREEN_HEIGHT))
        pygame.draw.rect(
            zone_surf, WALL_ZONE_COLOR, (SCREEN_WIDTH - d, 0, d, SCREEN_HEIGHT)
        )
        pygame.draw.rect(zone_surf, WALL_ZONE_COLOR, (0, 0, SCREEN_WIDTH, d))
        pygame.draw.rect(
            zone_surf, WALL_ZONE_COLOR, (0, SCREEN_HEIGHT - d, SCREEN_WIDTH, d)
        )
        self.screen.blit(zone_surf, (0, 0))

        if self.replay_mode:
            # Draw replay food
            for food in self.replay_food:
                pygame.draw.circle(
                    self.screen, FOOD_COLOR, (int(food[0]), int(food[1])), FOOD_RADIUS
                )
                pygame.draw.circle(
                    self.screen,
                    (255, 120, 120),
                    (int(food[0]), int(food[1])),
                    FOOD_RADIUS - 2,
                )
            if self.replay_individual:
                self.replay_individual.draw(self.screen, is_best=True)
            self._draw_replay_badge()
        else:
            best_ind = max(self.individuals, key=lambda i: i.network.fitness)

            # Coverage overlay — show best individual's visited cells
            cell_w = SCREEN_WIDTH / COVERAGE_COLS
            cell_h = SCREEN_HEIGHT / COVERAGE_ROWS
            cov_surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            for col, row in best_ind.visited:
                pygame.draw.rect(
                    cov_surf,
                    COVERAGE_COLOR,
                    (int(col * cell_w), int(row * cell_h), int(cell_w), int(cell_h)),
                )
            self.screen.blit(cov_surf, (0, 0))

            for ind in self.individuals:
                is_best = ind is best_ind
                a = 255 if is_best else GHOST_ALPHA

                # Draw this individual's remaining food (ghost opacity for non-best)
                for food in ind.food:
                    if is_best:
                        pygame.draw.circle(
                            self.screen,
                            FOOD_COLOR,
                            (int(food[0]), int(food[1])),
                            FOOD_RADIUS,
                        )
                        pygame.draw.circle(
                            self.screen,
                            (255, 120, 120),
                            (int(food[0]), int(food[1])),
                            FOOD_RADIUS - 2,
                        )
                    else:
                        tmp = pygame.Surface(
                            (FOOD_RADIUS * 2, FOOD_RADIUS * 2), pygame.SRCALPHA
                        )
                        pygame.draw.circle(
                            tmp,
                            (*FOOD_COLOR, a),
                            (FOOD_RADIUS, FOOD_RADIUS),
                            FOOD_RADIUS,
                        )
                        self.screen.blit(
                            tmp,
                            (int(food[0]) - FOOD_RADIUS, int(food[1]) - FOOD_RADIUS),
                        )

                ind.draw(self.screen, is_best=is_best, alpha=a)

            # Spawn point marker
            sx, sy = int(self.spawn_point[0]), int(self.spawn_point[1])
            pygame.draw.rect(
                self.screen,
                (80, 80, 80),
                pygame.Rect(
                    sx - INDIVIDUAL_SIZE,
                    sy - INDIVIDUAL_SIZE,
                    INDIVIDUAL_SIZE * 2,
                    INDIVIDUAL_SIZE * 2,
                ),
                1,
            )

        # HUD, speed badge and graph always visible
        self._draw_hud()
        self._draw_speed_badge()
        self._draw_graph()

        pygame.display.flip()

    # ------------------------------------------------------------------
    def _draw_hud(self):
        arch = (
            f"{INPUT_SIZE} → {' → '.join(str(h) for h in HIDDEN_SIZES)} → {OUTPUT_SIZE}"
        )
        mut_label = f"{self.current_mutation_rate:.3f}"
        if self.is_stagnating:
            mut_label += "  [BOOSTED]"
        lines = [
            ("Architecture", arch),
            ("Generation", str(self.generation)),
            (
                "Active",
                f"{sum(1 for i in self.individuals if not i.done)} / {POPULATION_SIZE}",
            ),
            ("Chain ×", f"{max(i.chain_mult for i in self.individuals)}"),
            (
                "Coverage",
                f"{max(len(i.visited) for i in self.individuals)} / {COVERAGE_COLS * COVERAGE_ROWS}",
            ),
            ("Best (gen)", f"{self.best_fitness_gen:.1f}"),
            ("Best (ever)", f"{self.best_fitness_ever:.1f}"),
            ("Stagnation", f"{self.stagnation_counter} / {STAGNATION_LIMIT}"),
            ("Mutation", mut_label),
            ("Time", f"{self.gen_time:.1f}s / {GENERATION_DURATION}s"),
        ]
        panel_w, panel_h = 300, len(lines) * 28 + 16
        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 160))
        self.screen.blit(panel, (8, 8))

        y = 16
        for label, value in lines:
            is_alert = label == "Mutation" and self.is_stagnating
            val_color = (255, 80, 80) if is_alert else HUD_ACCENT
            lbl_surf = self.font_sm.render(f"{label}:", True, HUD_COLOR)
            val_surf = self.font_sm.render(value, True, val_color)
            self.screen.blit(lbl_surf, (16, y))
            self.screen.blit(val_surf, (175, y))
            y += 28

        # Colour legend
        legend = [
            (INDIVIDUAL_BEST_CLR, "Best this gen"),
            (INDIVIDUAL_ELITE_CLR, f"Elite (top {ELITE_COUNT})"),
            (INDIVIDUAL_COLOR, "Normal"),
        ]
        ly = panel_h + 20
        for color, label in legend:
            pygame.draw.rect(self.screen, color, (16, ly, 14, 14))
            surf = self.font_sm.render(label, True, HUD_COLOR)
            self.screen.blit(surf, (36, ly))
            ly += 22

    # ------------------------------------------------------------------
    def _draw_speed_badge(self):
        if self.fast_forward:
            text = "⚡ FAST FORWARD"
            color = FAST_BADGE_COLOR
        else:
            text = "▶  NORMAL"
            color = SLOW_BADGE_COLOR

        surf = self.font_sm.render(f"[SPACE] {text}", True, color)
        rx = SCREEN_WIDTH - surf.get_width() - 16
        bg = pygame.Surface(
            (surf.get_width() + 16, surf.get_height() + 10), pygame.SRCALPHA
        )
        bg.fill((0, 0, 0, 160))
        self.screen.blit(bg, (rx - 8, 8))
        self.screen.blit(surf, (rx, 13))

    # ------------------------------------------------------------------
    def _draw_graph(self):
        """Bottom-right panel: best (yellow) and avg (grey) fitness per generation."""
        history = self.fitness_history[-GRAPH_MAX_POINTS:]
        if len(history) < 2:
            # Draw empty panel with label
            gx = SCREEN_WIDTH - GRAPH_W - 12
            gy = SCREEN_HEIGHT - GRAPH_H - 12
            panel = pygame.Surface((GRAPH_W, GRAPH_H), pygame.SRCALPHA)
            panel.fill((0, 0, 0, 180))
            self.screen.blit(panel, (gx, gy))
            lbl = self.font_sm.render("Fitness history", True, HUD_COLOR)
            self.screen.blit(lbl, (gx + 8, gy + 8))
            return

        gx = SCREEN_WIDTH - GRAPH_W - 12
        gy = SCREEN_HEIGHT - GRAPH_H - 12
        pad = 10  # inner padding

        panel = pygame.Surface((GRAPH_W, GRAPH_H), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 180))
        self.screen.blit(panel, (gx, gy))

        # Title
        lbl = self.font_sm.render("Fitness history", True, HUD_COLOR)
        self.screen.blit(lbl, (gx + pad, gy + 4))

        plot_x = gx + pad
        plot_y = gy + 22
        plot_w = GRAPH_W - pad * 2
        plot_h = GRAPH_H - 30

        all_vals = [v for pair in history for v in pair]
        max_val = max(all_vals) or 1.0

        def to_screen(i, val):
            sx = plot_x + int(i / (len(history) - 1) * plot_w)
            sy = plot_y + plot_h - int((val / max_val) * plot_h)
            return sx, sy

        # Draw avg line first (behind)
        for i in range(1, len(history)):
            pygame.draw.line(
                self.screen,
                GRAPH_AVG_COLOR,
                to_screen(i - 1, history[i - 1][1]),
                to_screen(i, history[i][1]),
                1,
            )
        # Draw best line on top
        for i in range(1, len(history)):
            pygame.draw.line(
                self.screen,
                GRAPH_BEST_COLOR,
                to_screen(i - 1, history[i - 1][0]),
                to_screen(i, history[i][0]),
                2,
            )

        # Legend dots
        lx = gx + GRAPH_W - 100
        ly = gy + 6
        pygame.draw.rect(self.screen, GRAPH_BEST_COLOR, (lx, ly, 10, 3))
        pygame.draw.rect(self.screen, GRAPH_AVG_COLOR, (lx, ly + 9, 10, 2))
        self.screen.blit(
            self.font_sm.render("best", True, GRAPH_BEST_COLOR), (lx + 14, ly - 3)
        )
        self.screen.blit(
            self.font_sm.render("avg", True, GRAPH_AVG_COLOR), (lx + 14, ly + 6)
        )

    # ------------------------------------------------------------------
    def _draw_replay_badge(self):
        """Prominent centred banner shown during replay."""
        text = "[ R ] — REPLAY: LAST GEN BEST"
        surf = self.font_lg.render(text, True, REPLAY_BADGE_COLOR)
        bw = surf.get_width() + 24
        bh = surf.get_height() + 12
        bx = (SCREEN_WIDTH - bw) // 2
        by = SCREEN_HEIGHT - bh - 14
        bg = pygame.Surface((bw, bh), pygame.SRCALPHA)
        bg.fill((0, 0, 0, 200))
        self.screen.blit(bg, (bx, by))
        self.screen.blit(surf, (bx + 12, by + 6))

        # Replay time
        t_surf = self.font_sm.render(
            f"run time: {self.replay_time:.1f}s   score: {self.replay_individual.network.fitness:.0f}",
            True,
            HUD_COLOR,
        )
        self.screen.blit(t_surf, (bx + 12, by - 22))

    # ------------------------------------------------------------------
    def run(self):
        dt = 1.0 / FPS  # logical tick size (fixed)

        while True:
            # ---- Events --------------------------------------------------
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_SPACE:
                        self.fast_forward = not self.fast_forward
                    if event.key == pygame.K_r:
                        if self.replay_mode:
                            self._exit_replay()
                        else:
                            self._enter_replay()
                    if event.key == pygame.K_ESCAPE:
                        pygame.quit()
                        sys.exit()

            # ---- Tick(s) -------------------------------------------------
            if self.replay_mode:
                # Replay always runs at normal speed (1 tick per frame)
                self._tick_replay(dt)
            else:
                ticks = FAST_TICKS_PER_FRAME if self.fast_forward else 1
                for _ in range(ticks):
                    self._tick(dt)
                    if self._generation_should_end():
                        self._evolve()
                        self._start_generation()
                        break

            # ---- Render --------------------------------------------------
            self._draw()
            self.clock.tick(FPS)


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    Simulation().run()
