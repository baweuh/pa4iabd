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
    assert cfg.agent.max_speed == pytest.approx(2.122)
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
    assert cfg.world.width == 3200
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


def test_reproduction_min_ticks_defaults_zero_when_omitted(raw: dict) -> None:
    # Backward-compatible addition: absent from every pre-existing config -> 0.
    raw["agent"].pop("reproduction_min_ticks", None)
    assert SimConfig.from_dict(raw).agent.reproduction_min_ticks == 0


def test_reproduction_min_ticks_parsed_when_present(raw: dict) -> None:
    raw["agent"]["reproduction_min_ticks"] = 60
    assert SimConfig.from_dict(raw).agent.reproduction_min_ticks == 60


def test_reproduction_min_ticks_rejects_negative(raw: dict) -> None:
    raw["agent"]["reproduction_min_ticks"] = -1
    with pytest.raises(ConfigError, match="reproduction_min_ticks must be >= 0"):
        SimConfig.from_dict(raw)


def test_max_children_per_tick_defaults_zero_when_omitted(raw: dict) -> None:
    # Backward-compatible addition: absent from every pre-existing config -> 0.
    raw["agent"].pop("max_children_per_tick", None)
    assert SimConfig.from_dict(raw).agent.max_children_per_tick == 0


def test_max_children_per_tick_parsed_when_present(raw: dict) -> None:
    raw["agent"]["max_children_per_tick"] = 2
    assert SimConfig.from_dict(raw).agent.max_children_per_tick == 2


def test_max_children_per_tick_rejects_negative(raw: dict) -> None:
    raw["agent"]["max_children_per_tick"] = -1
    with pytest.raises(ConfigError, match="max_children_per_tick must be >= 0"):
        SimConfig.from_dict(raw)


def test_reproduction_round_robin_defaults_false_when_omitted(raw: dict) -> None:
    raw["agent"].pop("reproduction_round_robin", None)
    assert SimConfig.from_dict(raw).agent.reproduction_round_robin is False


def test_reproduction_round_robin_parsed_when_present(raw: dict) -> None:
    raw["agent"]["reproduction_round_robin"] = True
    assert SimConfig.from_dict(raw).agent.reproduction_round_robin is True


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
    with pytest.raises(
        ConfigError, match="initial_size must be <= population.max_size"
    ):
        SimConfig.from_dict(raw)


def test_num_islands_defaults_one_when_omitted(raw: dict) -> None:
    assert "num_islands" not in raw["population"]
    cfg = SimConfig.from_dict(raw)
    assert cfg.population.num_islands == 1
    assert cfg.population.migration_interval_ticks == 500
    assert cfg.population.migration_count == 1


def test_num_islands_parsed_when_present(raw: dict) -> None:
    raw["population"]["num_islands"] = 4
    assert SimConfig.from_dict(raw).population.num_islands == 4


def test_num_islands_rejects_zero(raw: dict) -> None:
    raw["population"]["num_islands"] = 0
    with pytest.raises(ConfigError, match="num_islands must be >= 1"):
        SimConfig.from_dict(raw)


def test_num_islands_rejects_more_than_max_size(raw: dict) -> None:
    raw["population"]["num_islands"] = raw["population"]["max_size"] + 1
    with pytest.raises(ConfigError, match="num_islands must be <= population.max_size"):
        SimConfig.from_dict(raw)


def test_migration_interval_ticks_rejects_zero(raw: dict) -> None:
    raw["population"]["migration_interval_ticks"] = 0
    with pytest.raises(ConfigError, match="migration_interval_ticks must be >= 1"):
        SimConfig.from_dict(raw)


def test_migration_count_rejects_negative(raw: dict) -> None:
    raw["population"]["migration_count"] = -1
    with pytest.raises(ConfigError, match="migration_count must be >= 0"):
        SimConfig.from_dict(raw)


def test_diagnostics_optional_section_defaults(raw: dict) -> None:
    assert "diagnostics" not in raw
    cfg = SimConfig.from_dict(raw)
    assert cfg.diagnostics.capture_close_mult == 1.5
    assert cfg.diagnostics.capture_directed_ratio == 0.6
    assert cfg.diagnostics.capture_ahead_degrees == 90.0
    assert cfg.diagnostics.local_density_radius == 150.0
    assert cfg.diagnostics.ne_window_ticks == 1000
    assert cfg.diagnostics.forager_threshold == 0.1


def test_diagnostics_parsed_when_present(raw: dict) -> None:
    raw["diagnostics"] = {"ne_window_ticks": 2000, "local_density_radius": 75.0}
    cfg = SimConfig.from_dict(raw)
    assert cfg.diagnostics.ne_window_ticks == 2000
    assert cfg.diagnostics.local_density_radius == 75.0
    assert cfg.diagnostics.capture_close_mult == 1.5  # untouched default


def test_diagnostics_rejects_bad_ahead_degrees(raw: dict) -> None:
    raw["diagnostics"] = {"capture_ahead_degrees": 0.0}
    with pytest.raises(ConfigError, match="capture_ahead_degrees must be in"):
        SimConfig.from_dict(raw)


def test_diagnostics_rejects_zero_ne_window(raw: dict) -> None:
    raw["diagnostics"] = {"ne_window_ticks": 0}
    with pytest.raises(ConfigError, match="ne_window_ticks must be >= 1"):
        SimConfig.from_dict(raw)


def test_diagnostics_rejects_bad_directed_ratio(raw: dict) -> None:
    raw["diagnostics"] = {"capture_directed_ratio": 1.5}
    with pytest.raises(ConfigError, match="must be in \\[0, 1\\]"):
        SimConfig.from_dict(raw)


def test_diagnostics_rejects_non_positive_density_radius(raw: dict) -> None:
    raw["diagnostics"] = {"local_density_radius": 0.0}
    with pytest.raises(ConfigError, match="must be > 0"):
        SimConfig.from_dict(raw)


def test_hyperneat_optional_section_defaults(raw: dict) -> None:
    assert "hyperneat" not in raw
    cfg = SimConfig.from_dict(raw)
    assert cfg.hyperneat.enabled is False
    assert cfg.hyperneat.weight_scale == 3.0
    assert cfg.hyperneat.bootstrap_hidden_nodes == 0


def test_hyperneat_parsed_when_present(raw: dict) -> None:
    raw["hyperneat"] = {"enabled": True, "weight_scale": 5.0}
    cfg = SimConfig.from_dict(raw)
    assert cfg.hyperneat.enabled is True
    assert cfg.hyperneat.weight_scale == 5.0


def test_hyperneat_rejects_non_positive_weight_scale(raw: dict) -> None:
    raw["hyperneat"] = {"weight_scale": 0.0}
    with pytest.raises(ConfigError, match="weight_scale must be > 0"):
        SimConfig.from_dict(raw)


def test_hyperneat_bootstrap_hidden_nodes_parsed(raw: dict) -> None:
    raw["hyperneat"] = {"bootstrap_hidden_nodes": 2}
    cfg = SimConfig.from_dict(raw)
    assert cfg.hyperneat.bootstrap_hidden_nodes == 2


def test_hyperneat_rejects_negative_bootstrap_hidden_nodes(raw: dict) -> None:
    raw["hyperneat"] = {"bootstrap_hidden_nodes": -1}
    with pytest.raises(ConfigError, match="bootstrap_hidden_nodes must be >= 0"):
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


def test_hebbian_optional_section_defaults(raw: dict) -> None:
    assert "hebbian" not in raw
    cfg = SimConfig.from_dict(raw)
    assert cfg.hebbian.enabled is False
    assert cfg.hebbian.learning_rate == 0.01
    assert cfg.hebbian.weight_max == 5.0


def test_hebbian_parsed_when_present(raw: dict) -> None:
    raw["hebbian"] = {"enabled": True, "learning_rate": 0.05}
    cfg = SimConfig.from_dict(raw)
    assert cfg.hebbian.enabled is True
    assert cfg.hebbian.learning_rate == 0.05


def test_hebbian_rejects_non_positive_learning_rate(raw: dict) -> None:
    raw["hebbian"] = {"learning_rate": 0.0}
    with pytest.raises(ConfigError, match="learning_rate must be > 0"):
        SimConfig.from_dict(raw)


def test_hebbian_rejects_non_positive_weight_max(raw: dict) -> None:
    raw["hebbian"] = {"weight_max": -1.0}
    with pytest.raises(ConfigError, match="weight_max must be > 0"):
        SimConfig.from_dict(raw)
