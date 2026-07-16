"""Run a config to N ticks (seed-fixed) and report POPULATION-level foraging.

Unlike steer_probe (single champion genome, noisy under fast turnover), this
drives a full Simulation and measures the steering score across the whole final
living population — a robust signal of what the population actually evolved.

Usage: python -m tools.run_and_probe <config.yaml> <ticks> [label]
"""

from __future__ import annotations

import statistics as st
import sys
from random import Random

from src.config import SimConfig
from src.simulation import Simulation


def main(argv: list[str]) -> int:
    config_path = argv[1]
    ticks = int(argv[2])
    label = argv[3] if len(argv) > 3 else config_path
    cfg = SimConfig.from_yaml(config_path)

    seed = int(argv[4]) if len(argv) > 4 else cfg.simulation.seed
    sim = Simulation(cfg, Random(seed))
    while not sim.is_extinct and sim.tick_count < ticks:
        sim.tick()

    if sim.is_extinct:
        print(f"[{label}] EXTINCT at tick {sim.tick_count}")
        return 0

    pop = sim.population
    scores = [a.steer_score for a in pop]  # cached, see Agent.steer_score
    positive = sum(1 for s in scores if s > cfg.diagnostics.forager_threshold)

    print(
        f"[{label}] tick {sim.tick_count}  pop {len(pop)}  "
        f"record {sim.record_apples}  repro {sim.total_reproductions}"
    )
    print(
        f"  POPULATION steer score : mean {st.mean(scores):+.3f}  "
        f"median {st.median(scores):+.3f}  max {max(scores):+.3f}"
    )
    print(
        f"  agents steering toward apples (r>{cfg.diagnostics.forager_threshold}) : "
        f"{positive}/{len(pop)} ({100 * positive / len(pop):.0f}%)"
    )
    print(f"  hidden layer size (fixed) : {cfg.network.hidden_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
