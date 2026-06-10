"""Smoke tests for Renderer (Phase 7): headless init + 500 ticks + UI controls.

No display is required: SDL is forced to its dummy video driver before importing
the renderer, so these run in CI/WSL. Pygame rendering is graphical, so this is a
crash/smoke suite, not a pixel-level assertion suite.
"""

# pylint: disable=missing-function-docstring,protected-access,redefined-outer-name

from __future__ import annotations

import copy
import os
from pathlib import Path

import pytest
import yaml

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402  pylint: disable=wrong-import-position

from src.config import SimConfig  # noqa: E402
from src.renderer import (  # noqa: E402
    SPEED_MAX,
    SPEED_MIN,
    Renderer,
)

DEFAULT_YAML = Path(__file__).resolve().parents[1] / "config" / "default.yaml"


def build_config(tmp_path: Path, **overrides: dict) -> SimConfig:
    """Default config with section overrides and logging redirected to tmp_path."""
    raw = copy.deepcopy(yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8")))
    raw["logging"]["csv_path"] = str(tmp_path / "metrics.csv")
    raw["logging"]["best_genome_path"] = str(tmp_path / "best_genome.json")
    for section, values in overrides.items():
        raw[section].update(values)
    return SimConfig.from_dict(raw)


@pytest.fixture(name="renderer")
def renderer_fixture(tmp_path):
    cfg = build_config(tmp_path)
    rend = Renderer(cfg)
    yield rend
    pygame.quit()  # pylint: disable=no-member


def test_init_no_pygame_import_error(renderer):
    assert renderer.sim.population_size == renderer._config.population.initial_size
    assert renderer.ticks_per_frame == SPEED_MIN
    assert renderer.paused is False
    assert len(renderer._buttons) == 5


def test_smoke_500_ticks_with_ui(renderer):
    for _ in range(500):
        renderer.sim.tick()
        renderer._draw()
    assert len(renderer.sim.population) > 0
    assert renderer.sim.food_available > 0
    assert renderer.sim.tick_count == 500


def test_speed_controls_clamp(renderer):
    for _ in range(10):
        renderer._speed_up()
    assert renderer.ticks_per_frame == SPEED_MAX
    for _ in range(10):
        renderer._speed_down()
    assert renderer.ticks_per_frame == SPEED_MIN


def test_pause_toggle(renderer):
    assert renderer.paused is False
    renderer._handle_key(pygame.K_SPACE)  # pylint: disable=no-member
    assert renderer.paused is True
    renderer._handle_key(pygame.K_SPACE)  # pylint: disable=no-member
    assert renderer.paused is False


def test_button_click_changes_speed(renderer):
    fast_up = renderer._buttons[">>"]
    renderer._handle_click(fast_up.center)
    assert renderer.ticks_per_frame == 2
    fast_down = renderer._buttons["<<"]
    renderer._handle_click(fast_down.center)
    assert renderer.ticks_per_frame == SPEED_MIN
