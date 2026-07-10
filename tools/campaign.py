"""Run a multi-seed campaign in parallel and print the verdict table.

Lever 1 of the poc2.4 perf chantier. Each seed is a fully independent
``Simulation`` (its own ``Random(seed)``, no shared state), so seeds run in
separate processes with near-linear speedup and bit-identical results to a
sequential run — determinism is preserved (invariant n°1 untouched: the YAML
stays the source of truth, only ``--seed``/``--ticks`` are overridden as in
``main.py``).

Mirrors the metrics of ``tools.run_and_probe`` (population steering score,
share of foragers r>0.1, mean hidden nodes) so a campaign reads exactly like
the verdict tables in the audits.

Usage:
    python -m tools.campaign <config.yaml> <ticks> [seed,seed,...] [--workers N]

Default seed trio is the campaign standard 42,7,123.
"""

from __future__ import annotations

import argparse
import os
import statistics as st
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from random import Random

from src.config import SimConfig
from src.simulation import Simulation
from tools.steer_probe import steer_score

DEFAULT_SEEDS = (42, 7, 123)


@dataclass
class SeedResult:
    """Final metrics for one seed's run (mirrors run_and_probe's report)."""

    seed: int
    ticks: int
    extinct: bool
    pop: int
    record: int
    repro: int
    steer_mean: float
    steer_median: float
    forager_pct: float
    hidden_mean: float


def _run_seed(args: tuple[str, int, int]) -> SeedResult:
    """Worker: run one seed to ``ticks`` and return its metrics."""
    config_path, ticks, seed = args
    cfg = SimConfig.from_yaml(config_path)
    sim = Simulation(cfg, Random(seed))
    while not sim.is_extinct and sim.tick_count < ticks:
        sim.tick()

    if sim.is_extinct or not sim.population:
        return SeedResult(
            seed,
            sim.tick_count,
            True,
            0,
            sim.record_apples,
            sim.total_reproductions,
            0.0,
            0.0,
            0.0,
            0.0,
        )

    pop = sim.population
    scores = [steer_score(a.network, cfg.sensors) for a in pop]
    hiddens = [sum(1 for n in a.genome.nodes if n.node_type == "hidden") for a in pop]
    positive = sum(1 for s in scores if s > 0.1)
    return SeedResult(
        seed,
        sim.tick_count,
        False,
        len(pop),
        sim.record_apples,
        sim.total_reproductions,
        st.mean(scores),
        st.median(scores),
        100.0 * positive / len(pop),
        st.mean(hiddens),
    )


def main() -> int:
    """Parse args, run the seeds in parallel, print the verdict table."""
    parser = argparse.ArgumentParser(description="Parallel multi-seed campaign.")
    parser.add_argument("config")
    parser.add_argument("ticks", type=int)
    parser.add_argument(
        "seeds",
        nargs="?",
        default=None,
        help="comma-separated seeds (default 42,7,123)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="max parallel processes (default: min(#seeds, cores-1))",
    )
    args = parser.parse_args()

    seeds = (
        [int(s) for s in args.seeds.split(",")] if args.seeds else list(DEFAULT_SEEDS)
    )
    workers = args.workers or min(len(seeds), max(1, (os.cpu_count() or 2) - 1))

    print(
        f"campaign: {args.config}  ticks={args.ticks}  "
        f"seeds={seeds}  workers={workers}"
    )
    t0 = time.perf_counter()
    jobs = [(args.config, args.ticks, s) for s in seeds]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        results = sorted(ex.map(_run_seed, jobs), key=lambda r: seeds.index(r.seed))
    dt = time.perf_counter() - t0

    print(
        f"\n{'seed':>6} {'pop':>5} {'record':>7} {'repro':>7} "
        f"{'steer_med':>10} {'foragers%':>10} {'hidden':>7}"
    )
    for r in results:
        if r.extinct:
            print(f"{r.seed:>6}  EXTINCT at tick {r.ticks}")
            continue
        print(
            f"{r.seed:>6} {r.pop:>5} {r.record:>7} {r.repro:>7} "
            f"{r.steer_median:>+10.3f} {r.forager_pct:>9.0f}% {r.hidden_mean:>7.2f}"
        )

    alive = [r for r in results if not r.extinct]
    if alive:
        mean_forage = st.mean(r.forager_pct for r in alive)
        print(f"\n  mean foragers across {len(alive)} seed(s): {mean_forage:.0f}%")
    print(f"  wall-clock: {dt:.1f}s ({len(seeds)} seeds, {workers} workers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
