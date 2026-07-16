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
        [--progress-interval SECONDS] [--quiet]

Default seed trio is the campaign standard 42,7,123. Progress (one plain text
line per interval, all seeds' tick counts) prints every 10s by default —
deliberately not a carriage-return progress bar, since campaigns are commonly
run in the background with output piped to a log file, where a discrete line
per update is what stays readable. Pass --quiet to suppress it.
"""

from __future__ import annotations

import argparse
import os
import statistics as st
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace
from multiprocessing import Manager
from pathlib import Path
from random import Random

from src.config import SimConfig
from src.simulation import Simulation
from tools.steer_probe import steer_score

DEFAULT_SEEDS = (42, 7, 123)
DEFAULT_PROGRESS_INTERVAL_SECONDS = 10.0
PROGRESS_REPORTS_PER_SEED = 200  # ~0.5% resolution, negligible IPC overhead


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


def _per_seed_config(cfg: SimConfig, seed: int) -> SimConfig:
    """Redirect CSV/best-genome output to a seed-exclusive subfolder.

    ``Simulation._run_id`` has SECOND resolution (``datetime.now()``), and a
    campaign launches every seed's process at essentially the same instant —
    without this, parallel seeds sharing a run_id would all write CSV rows
    and best-genome JSON files to the SAME ``logs/<run_id>/`` folder,
    corrupting each other's output. Giving each seed its own subfolder (under
    the config's configured ``logging.csv_path``) makes every seed's
    ``_run_dir()`` distinct regardless of run_id collisions.
    """
    base = Path(cfg.logging.csv_path)
    seed_dir = base.parent / f"seed{seed}"
    return replace(
        cfg,
        logging=replace(
            cfg.logging,
            csv_path=str(seed_dir / base.name),
            best_genome_path=str(seed_dir / Path(cfg.logging.best_genome_path).name),
        ),
    )


def _run_seed(args: tuple[str, int, int, "dict[int, int] | None"]) -> SeedResult:
    """Worker: run one seed to ``ticks``, report progress, return its metrics.

    Drives the CSV logger throughout (like ``main.py``'s headless mode), so
    every campaign now produces the full extended-diagnostics CSV per seed
    (``logs/.../seed<N>/<run_id>/metrics.csv``) for post-hoc analysis, not
    just this function's own end-of-run verdict snapshot.
    """
    config_path, ticks, seed, progress = args
    report_every = max(1, ticks // PROGRESS_REPORTS_PER_SEED)
    cfg = _per_seed_config(SimConfig.from_yaml(config_path), seed)
    sim = Simulation(cfg, Random(seed))
    sim.open_csv_logger()
    try:
        while not sim.is_extinct and sim.tick_count < ticks:
            sim.tick()
            if progress is not None and sim.tick_count % report_every == 0:
                progress[seed] = sim.tick_count
    finally:
        sim.close_csv_logger()
    if progress is not None:
        progress[seed] = sim.tick_count

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
    # poc3: topology is fixed by config, never mutated structurally — every
    # agent has exactly network.hidden_size hidden units, always (no longer
    # an emergent per-agent metric like it was under NEAT).
    positive = sum(1 for s in scores if s > cfg.diagnostics.forager_threshold)
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
        float(cfg.network.hidden_size),
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
    parser.add_argument(
        "--progress-interval",
        type=float,
        default=DEFAULT_PROGRESS_INTERVAL_SECONDS,
        help="seconds between progress lines "
        f"(default {DEFAULT_PROGRESS_INTERVAL_SECONDS})",
    )
    parser.add_argument(
        "--quiet", action="store_true", help="suppress periodic progress lines"
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
    with Manager() as manager:
        progress = manager.dict({s: 0 for s in seeds})
        jobs = [(args.config, args.ticks, s, progress) for s in seeds]
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(_run_seed, job) for job in jobs]
            while not args.quiet:
                elapsed = time.perf_counter() - t0
                status = "  ".join(
                    f"{s}:{progress[s]:>{len(str(args.ticks))}}/{args.ticks}"
                    f"({100 * progress[s] // args.ticks:>3}%)"
                    for s in seeds
                )
                print(f"[{elapsed:6.1f}s] {status}", flush=True)
                if all(f.done() for f in futures):
                    break
                time.sleep(args.progress_interval)
            results = sorted(
                (f.result() for f in futures), key=lambda r: seeds.index(r.seed)
            )
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
