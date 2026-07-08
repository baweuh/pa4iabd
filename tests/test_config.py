"""Tests for the typed configuration loader."""

from __future__ import annotations

import copy
import dataclasses
from pathlib import Path

import pytest
import yaml

from src.config import ConfigError, SimConfig

DEFAULT_YAML = Path(__file__).resolve().parents[1] / "config" / "default.yaml"


@pytest.fixture(name="raw")
def raw_fixture() -> dict:
    """Parsed contents of the default config as a plain dict."""
    return yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))


def test_load_default_yaml() -> None:
    cfg = SimConfig.from_yaml(DEFAULT_YAML)
    assert isinstance(cfg, SimConfig)
    assert cfg.agent.max_speed == pytest.approx(4.243)
    assert cfg.sensors.num_rays == 16
    assert cfg.network.activation == "tanh"


def test_inputs_consistency() -> None:
    cfg = SimConfig.from_yaml(DEFAULT_YAML)
    assert cfg.network.num_inputs == cfg.sensors.num_inputs


def test_frozen() -> None:
    cfg = SimConfig.from_yaml(DEFAULT_YAML)
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.agent.max_speed = 9.0  # type: ignore[misc]


def test_from_dict(raw: dict) -> None:
    cfg = SimConfig.from_dict(raw)
    assert cfg.world.width == 2263
    assert cfg.population.initial_size == 200


def test_missing_file() -> None:
    with pytest.raises(ConfigError, match="cannot read config file"):
        SimConfig.from_yaml("does/not/exist.yaml")


def test_missing_section(raw: dict) -> None:
    del raw["agent"]
    with pytest.raises(ConfigError, match="missing config section 'agent'"):
        SimConfig.from_dict(raw)


def test_missing_key(raw: dict) -> None:
    del raw["agent"]["max_speed"]
    with pytest.raises(ConfigError, match="missing key"):
        SimConfig.from_dict(raw)


def test_unknown_key(raw: dict) -> None:
    raw["agent"]["bogus"] = 1
    with pytest.raises(ConfigError, match="unknown key"):
        SimConfig.from_dict(raw)


def test_local_validation_negative(raw: dict) -> None:
    raw["agent"]["max_speed"] = -1.0
    with pytest.raises(ConfigError, match="must be > 0"):
        SimConfig.from_dict(raw)


def test_local_validation_rate(raw: dict) -> None:
    raw["genome"]["weight_mutation_rate"] = 1.5
    with pytest.raises(ConfigError, match="must be in"):
        SimConfig.from_dict(raw)


def test_apple_respawn_delay_loaded(raw: dict) -> None:
    cfg = SimConfig.from_dict(raw)
    assert cfg.apple.respawn_delay == 150


def test_apple_respawn_delay_must_be_positive(raw: dict) -> None:
    raw["apple"]["respawn_delay"] = 0
    with pytest.raises(ConfigError, match="must be > 0"):
        SimConfig.from_dict(raw)


def test_cross_validation_inputs(raw: dict) -> None:
    raw["network"]["num_inputs"] = 10
    with pytest.raises(ConfigError, match="num_inputs"):
        SimConfig.from_dict(raw)


def test_cross_validation_zone_too_large(raw: dict) -> None:
    raw["penalty_zone"]["width"] = 10_000
    with pytest.raises(ConfigError, match="penalty_zone.width"):
        SimConfig.from_dict(raw)


def test_cross_validation_reproduction(raw: dict) -> None:
    raw["agent"]["reproduction_cost"] = raw["agent"]["reproduction_threshold"] + 1
    with pytest.raises(ConfigError, match="reproduction_cost"):
        SimConfig.from_dict(raw)


def test_cross_validation_population(raw: dict) -> None:
    raw["population"]["initial_size"] = raw["population"]["max_size"] + 1
    with pytest.raises(ConfigError, match="population sizes"):
        SimConfig.from_dict(raw)


def test_invalid_yaml(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("world: [unclosed", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid YAML"):
        SimConfig.from_yaml(bad)


def test_deepcopy_isolation(raw: dict) -> None:
    # Guard against fixtures sharing mutable state across tests.
    snapshot = copy.deepcopy(raw)
    raw["agent"]["max_speed"] = 99.0
    assert snapshot["agent"]["max_speed"] != raw["agent"]["max_speed"]
