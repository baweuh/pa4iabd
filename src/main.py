"""Command-line entry point: dispatch to the visual demo or a headless run.

Phase 8 ties Phases 1-7 together behind an ``argparse`` CLI. Two modes:

- ``visual`` (default): the Pygame :class:`Renderer` demo (interactive speed
  controls, HUD, end-of-life colouring). The primary experience.
- ``headless``: a pure :class:`Simulation` loop with no Pygame, printing
  progress every ``logging.log_interval_ticks`` and writing the metrics CSV.
  For tests and parameter calibration.

Invariant n°1 (YAML is the source of truth) is preserved: ``--seed``/``--ticks``
default to ``None`` and only override the config when explicitly passed; the
override is applied immutably via :func:`dataclasses.replace`, which re-runs the
config validation.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys

from src.config import ConfigError, SimConfig
from src.simulation import Simulation

DEFAULT_CONFIG_PATH = "config/default.yaml"


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser (``--mode/--seed/--ticks/--config``)."""
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="ALife neuroevolution simulation — visual demo or headless run.",
    )
    parser.add_argument(
        "--mode",
        choices=("visual", "headless"),
        default="visual",
        help="visual: Pygame demo (default). headless: no rendering, CSV + progress.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="RNG seed (overrides config; default: simulation.seed from YAML).",
    )
    parser.add_argument(
        "--ticks",
        type=int,
        default=None,
        help="Tick budget, headless only (overrides config; 0 = until extinction).",
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to the YAML config (default: {DEFAULT_CONFIG_PATH}).",
    )
    return parser


def resolve_config(path: str, seed: int | None, ticks: int | None) -> SimConfig:
    """Load the YAML config and apply explicit CLI overrides immutably.

    ``seed``/``ticks`` of ``None`` keep the YAML value. ``dataclasses.replace``
    rebuilds the frozen sections and re-runs validation (e.g. ``max_ticks >= 0``).
    Raises :class:`ConfigError` on a missing/invalid file or invalid override.
    """
    config = SimConfig.from_yaml(path)
    if seed is None and ticks is None:
        return config
    simulation = dataclasses.replace(
        config.simulation,
        seed=seed if seed is not None else config.simulation.seed,
        max_ticks=ticks if ticks is not None else config.simulation.max_ticks,
    )
    return dataclasses.replace(config, simulation=simulation)


def run_visual(config: SimConfig) -> None:
    """Launch the interactive Pygame renderer (imported lazily)."""
    # Imported here so headless runs (and headless CI) never require Pygame.
    from src.renderer import Renderer  # pylint: disable=import-outside-toplevel

    Renderer(config).run()


def run_headless(config: SimConfig) -> None:
    """Drive a pure simulation loop, printing progress and writing the CSV."""
    sim = Simulation(config)
    interval = config.logging.log_interval_ticks
    max_ticks = config.simulation.max_ticks  # 0 == until extinction / Ctrl+C
    print(
        f"Headless run — seed {config.simulation.seed}, "
        f"max_ticks {max_ticks or '∞'}."
    )
    sim.open_csv_logger()
    try:
        while not sim.is_extinct:
            if max_ticks and sim.tick_count >= max_ticks:
                break
            sim.tick()
            if sim.tick_count % interval == 0:
                print(
                    f"Tick: {sim.tick_count:6d} | Pop: {sim.population_size:3d} "
                    f"| Food: {sim.food_available:3d}"
                )
        if sim.is_extinct:
            print("Population extinct.")
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        sim.close_csv_logger()
    print(f"Simulation complete. Check {config.logging.csv_path} for CSV.")


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, resolve the config and dispatch to the chosen mode."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.ticks is not None and args.mode == "visual":
        parser.error("--ticks is only valid with --mode headless")
    if args.seed is not None and args.seed < 0:
        parser.error("--seed must be >= 0")

    try:
        config = resolve_config(args.config, args.seed, args.ticks)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    if args.mode == "visual":
        run_visual(config)
    else:
        run_headless(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
