"""Tests for the Phase 8 CLI (src/main.py): modes, overrides, determinism.

SDL is forced to its dummy video driver before importing the renderer so the
visual-init smoke runs headless in CI/WSL. The CLI functions are exercised
directly (no subprocess) via ``main``/``resolve_config``/``run_headless``.
"""

# pylint: disable=missing-function-docstring,protected-access,redefined-outer-name

from __future__ import annotations

import copy
import os
from pathlib import Path
from random import Random

import pytest
import yaml

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from src.config import SimConfig  # noqa: E402
from src.main import (  # noqa: E402
    _fit_scale,
    main,
    resolve_config,
    run_headless,
)
from src.simulation import Simulation  # noqa: E402

DEFAULT_YAML = Path(__file__).resolve().parents[1] / "config" / "default.yaml"


def build_config(tmp_path: Path, **overrides: dict) -> SimConfig:
    """Default config with section overrides and logging redirected to tmp_path."""
    raw = copy.deepcopy(yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8")))
    raw["logging"]["csv_path"] = str(tmp_path / "metrics.csv")
    raw["logging"]["best_genome_path"] = str(tmp_path / "best_genome.json")
    for section, values in overrides.items():
        raw[section].update(values)
    return SimConfig.from_dict(raw)


def write_config(tmp_path: Path, **overrides: dict) -> Path:
    """Materialise a config YAML under tmp_path and return its path."""
    raw = copy.deepcopy(yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8")))
    raw["logging"]["csv_path"] = str(tmp_path / "metrics.csv")
    raw["logging"]["best_genome_path"] = str(tmp_path / "best_genome.json")
    for section, values in overrides.items():
        raw[section].update(values)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return path


# ------------------------------------------------------------------ #
# Visual mode init (smoke)
# ------------------------------------------------------------------ #


def test_visual_mode_init(tmp_path):
    import pygame  # pylint: disable=import-outside-toplevel
    from src.renderer import Renderer  # pylint: disable=import-outside-toplevel

    cfg = build_config(tmp_path)
    rend = Renderer(cfg)
    try:
        assert rend.sim.population_size == cfg.population.initial_size
    finally:
        pygame.quit()  # pylint: disable=no-member


# ------------------------------------------------------------------ #
# Headless mode
# ------------------------------------------------------------------ #


def test_headless_mode_500_ticks(tmp_path):
    cfg = build_config(tmp_path, simulation={"max_ticks": 500})
    run_headless(cfg)
    # CSV is inside logs/<run_id>/metrics.csv — find it via glob.
    log_dir = Path(cfg.logging.csv_path).parent
    csvs = list(log_dir.glob("*/metrics.csv"))
    assert len(csvs) == 1
    rows = csvs[0].read_text(encoding="utf-8").splitlines()
    assert len(rows) > 1  # header + at least one logged row


def test_headless_progress_output(tmp_path, capsys):
    cfg = build_config(tmp_path, simulation={"max_ticks": 200})
    run_headless(cfg)
    out = capsys.readouterr().out
    assert "Tick:" in out
    assert "Simulation complete" in out


# ------------------------------------------------------------------ #
# CLI argument validation
# ------------------------------------------------------------------ #


def test_cli_headless_invalid_ticks(tmp_path):
    path = write_config(tmp_path)
    with pytest.raises(SystemExit):
        main(["--mode", "visual", "--ticks", "100", "--config", str(path)])


def test_cli_invalid_seed(tmp_path):
    path = write_config(tmp_path)
    with pytest.raises(SystemExit):
        main(["--mode", "headless", "--seed", "-1", "--config", str(path)])


def test_cli_missing_config_returns_error_code():
    assert main(["--mode", "headless", "--ticks", "1", "--config", "no_such.yaml"]) == 2


# ------------------------------------------------------------------ #
# Config override (CLI -> YAML fallback)
# ------------------------------------------------------------------ #


def test_seed_override(tmp_path):
    path = write_config(tmp_path, simulation={"seed": 42})
    cfg = resolve_config(str(path), seed=999, ticks=None)
    assert cfg.simulation.seed == 999


def test_override_none_keeps_yaml(tmp_path):
    path = write_config(tmp_path, simulation={"seed": 7, "max_ticks": 3})
    cfg = resolve_config(str(path), seed=None, ticks=None)
    assert cfg.simulation.seed == 7
    assert cfg.simulation.max_ticks == 3


# ------------------------------------------------------------------ #
# Determinism
# ------------------------------------------------------------------ #


def _population_curve(cfg: SimConfig, ticks: int, interval: int) -> list[int]:
    sim = Simulation(cfg, Random(cfg.simulation.seed))
    curve: list[int] = []
    for _ in range(ticks):
        sim.tick()
        if sim.tick_count % interval == 0:
            curve.append(sim.population_size)
    return curve


def test_seed_determinism(tmp_path):
    cfg = build_config(tmp_path, simulation={"seed": 123})
    curves = [_population_curve(cfg, 300, 50) for _ in range(3)]
    assert curves[0] == curves[1] == curves[2]
    assert curves[0]  # non-empty sanity check


# ------------------------------------------------------------------ #
# Adaptive window scaling (pure helper — no display needed)
# ------------------------------------------------------------------ #


def test_fit_scale_no_scaling_when_window_fits():
    assert _fit_scale(1600, 900, 1920, 1080) == 1.0
    assert _fit_scale(1600, 900, 1600, 900) == 1.0


def test_fit_scale_downscales_preserving_ratio():
    # 1366x768 screen minus the 50px taskbar margin.
    scale = _fit_scale(1600, 900, 1316, 718)
    assert scale < 1.0
    assert scale == pytest.approx(min(1316 / 1600, 718 / 900))
    # Same factor on both axes => 16:9 preserved.
    assert (1600 * scale) / (900 * scale) == pytest.approx(16 / 9)
    # Both scaled dimensions land within the available area.
    assert 1600 * scale <= 1316 + 1e-9
    assert 900 * scale <= 718 + 1e-9
