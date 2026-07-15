"""Instrument a real run to classify HOW apples get eaten (Robin, 2026-07-09):
does the crowded population actually forage toward apples, or do agents mostly
stumble onto them via undirected trajectories in an overcrowded map?

Monkeypatches ``Agent.eat`` for the lifetime of this process only (never
touches src/) to log, per capture: the apple's lifetime since it last spawned
(read off ``Apple.spawn_tick``, stamped natively by
``Environment.tick_respawns``), and the 3-way classification from
``src.diagnostics.classify_capture`` (adjacent/directed/undirected — see its
docstring), independently reconstructed here rather than read off the live
Simulation's own ``_capture_counts``: an external cross-check of the same
logic, not just a check that the wiring calls it.

Usage: python -m tools.apple_capture_probe <config.yaml> <ticks> [warmup] [seed]
       [lookback]
``lookback`` defaults to ``src.diagnostics.capture_lookback_ticks`` (derived
from ``sensors.max_distance``/``agent.max_speed``) rather than a fixed magic
number — the same fix applied to the migrated in-simulation classifier.
"""

from __future__ import annotations

import math
import statistics as st
import sys
from collections import deque
from random import Random

from src.agent import Agent
from src.config import SimConfig
from src.diagnostics import capture_lookback_ticks, classify_capture
from src.simulation import Simulation


def main(argv: list[str]) -> int:
    config_path = argv[1]
    ticks = int(argv[2])
    warmup = int(argv[3]) if len(argv) > 3 else ticks // 3
    cfg = SimConfig.from_yaml(config_path)
    seed = int(argv[4]) if len(argv) > 4 else cfg.simulation.seed
    lookback = (
        int(argv[5])
        if len(argv) > 5
        else capture_lookback_ticks(cfg.sensors, cfg.agent)
    )

    sim = Simulation(cfg, Random(seed))
    reach = cfg.agent.radius + cfg.apple.radius
    tps = cfg.simulation.ticks_per_second

    events: list[tuple[int, str]] = []
    history: dict[int, deque] = {}

    original_eat = Agent.eat

    def eat_probe(self: Agent) -> list:
        candidates = [
            apple
            for apple in self._env.apples  # pylint: disable=protected-access
            if math.hypot(apple.x - self.x, apple.y - self.y) <= reach
        ]
        eaten = original_eat(self)
        if candidates and sim.tick_count >= warmup:
            hist = history[id(self)]
            for apple in candidates:
                born = apple.spawn_tick  # native since Environment.tick_respawns
                # Reference point = agent's position at (or just after) the
                # apple's own spawn tick, not a fixed lookback: approaching a
                # spot before the apple existed there isn't "directed" toward it.
                _, x0, y0, h0 = hist[0]
                for entry in hist:
                    if entry[0] >= born:
                        _, x0, y0, h0 = entry
                        break
                category = classify_capture(
                    apple.x, apple.y, x0, y0, h0, reach, cfg.diagnostics
                )
                events.append((sim.tick_count - born, category))
        return eaten

    Agent.eat = eat_probe  # type: ignore[method-assign]

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
