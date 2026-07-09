"""Instrument a real run to classify HOW apples get eaten (Robin, 2026-07-09):
does the crowded population actually forage toward apples, or do agents mostly
stumble onto them via undirected trajectories in an overcrowded map?

Monkeypatches ``Agent.eat`` and ``Environment.tick_respawns`` for the lifetime
of this process only (never touches src/) to log, per capture: the apple's
lifetime since it last spawned, and a 3-way classification looking
``lookback`` ticks into the agent's past:

  adjacent   - agent was already within ~1.5x eating reach of the apple back
               then (no real travel needed: a "free" apple).
  directed   - apple was ahead (egocentric bearing) and the agent closed most
               of the gap: genuine steering toward it.
  undirected - apple was reached without a clear directed approach (behind /
               to the side, or distance didn't meaningfully close): consistent
               with a random-walk collision rather than skill.

Usage: python -m tools.apple_capture_probe <config.yaml> <ticks> [warmup] [seed] [lookback]
"""

from __future__ import annotations

import math
import statistics as st
import sys
from collections import deque
from random import Random

from src.agent import Agent
from src.config import SimConfig
from src.environment import Environment
from src.simulation import Simulation

# Classification heuristics (analysis-only, not simulation parameters).
_CLOSE_MULT = 1.5  # "adjacent" if the apple was already within this * reach
_DIRECTED_RATIO = 0.6  # fraction of the initial gap that must close to call it directed
_AHEAD_DEG = 90.0  # forward half-plane, egocentric


def main(argv: list[str]) -> int:
    config_path = argv[1]
    ticks = int(argv[2])
    warmup = int(argv[3]) if len(argv) > 3 else ticks // 3
    cfg = SimConfig.from_yaml(config_path)
    seed = int(argv[4]) if len(argv) > 4 else cfg.simulation.seed
    lookback = int(argv[5]) if len(argv) > 5 else 30

    sim = Simulation(cfg, Random(seed))
    reach = cfg.agent.radius + cfg.apple.radius
    tps = cfg.simulation.ticks_per_second

    events: list[tuple[int, str]] = []
    spawn_tick: dict[int, int] = {id(a): 0 for a in sim.env.apples}
    history: dict[int, deque] = {}

    original_eat = Agent.eat
    original_respawns = Environment.tick_respawns

    def eat_probe(self: Agent) -> int:
        candidates = [
            apple
            for apple in self._env.apples  # pylint: disable=protected-access
            if math.hypot(apple.x - self.x, apple.y - self.y) <= reach
        ]
        eaten = original_eat(self)
        if candidates and sim.tick_count >= warmup:
            hist = history[id(self)]
            for apple in candidates:
                born = spawn_tick.get(id(apple), 0)
                # Reference point = agent's position at (or just after) the
                # apple's own spawn tick, not a fixed lookback: approaching a
                # spot before the apple existed there isn't "directed" toward it.
                _, x0, y0, h0 = hist[0]
                for entry in hist:
                    if entry[0] >= born:
                        _, x0, y0, h0 = entry
                        break
                dist0 = math.hypot(apple.x - x0, apple.y - y0)
                if dist0 <= reach * _CLOSE_MULT:
                    category = "adjacent"
                else:
                    bearing = math.atan2(apple.y - y0, apple.x - x0) - h0
                    bearing = (bearing + math.pi) % (2 * math.pi) - math.pi
                    ahead = abs(math.degrees(bearing)) <= _AHEAD_DEG
                    ratio = max(0.0, (dist0 - reach) / dist0)
                    category = (
                        "directed"
                        if (ahead and ratio >= _DIRECTED_RATIO)
                        else "undirected"
                    )
                events.append((sim.tick_count - born, category))
        return eaten

    def respawns_probe(self: Environment, rng: Random) -> None:
        before = {id(a) for a in self.apples}
        original_respawns(self, rng)
        for apple in self.apples:
            if id(apple) not in before:
                spawn_tick[id(apple)] = sim.tick_count + 1

    Agent.eat = eat_probe  # type: ignore[method-assign]
    Environment.tick_respawns = respawns_probe  # type: ignore[method-assign]

    try:
        while not sim.is_extinct and sim.tick_count < ticks:
            for agent in sim.population:
                h = history.setdefault(id(agent), deque(maxlen=lookback + 1))
                h.append((sim.tick_count, agent.x, agent.y, agent.heading))
            sim.tick()
            alive = {id(a) for a in sim.population}
            for agent_id in [aid for aid in history if aid not in alive]:
                del history[agent_id]
    finally:
        Agent.eat = original_eat  # type: ignore[method-assign]
        Environment.tick_respawns = original_respawns  # type: ignore[method-assign]

    if sim.is_extinct:
        print(f"EXTINCT at tick {sim.tick_count}")
        return 0

    if not events:
        print(f"No captures logged after warmup={warmup} (ticks={sim.tick_count}).")
        return 0

    lifetimes = [e[0] for e in events]
    cats = [e[1] for e in events]
    n = len(events)
    print(
        f"tick {sim.tick_count}  pop {sim.population_size}/{cfg.population.max_size}  "
        f"food {sim.food_available}/{cfg.apple.count}  captures logged {n} "
        f"(post-warmup={warmup})"
    )
    print(
        f"  apple lifetime (ticks): mean {st.mean(lifetimes):.1f} "
        f"({st.mean(lifetimes) / tps:.2f}s)  median {st.median(lifetimes):.1f}  "
        f"min {min(lifetimes)}  max {max(lifetimes)}"
    )
    for label in ("adjacent", "directed", "undirected"):
        count = cats.count(label)
        print(f"  {label:<10}: {count:>5} ({100 * count / n:.0f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
