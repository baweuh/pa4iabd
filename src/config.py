"""Typed, immutable simulation configuration loaded from YAML.

Every tunable parameter in the project lives here and is read through a
``SimConfig`` instance (invariant n°1: no magic numbers in code). The config
is split into one frozen dataclass per domain, mapped 1:1 onto the sections of
``config/default.yaml``.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

import yaml


class ConfigError(Exception):
    """Raised when a configuration file is missing, malformed or invalid."""


@dataclass(frozen=True)
class WorldConfig:
    """Dimensions of the toroidal-free, walled world (pixels)."""

    width: float
    height: float

    def __post_init__(self) -> None:
        _require_positive(self, "width", "height")


@dataclass(frozen=True)
class PenaltyZoneConfig:
    """Energy-draining border zone near the walls."""

    width: float  # thickness from the wall, in pixels
    max_drain: float  # energy drained per tick at the wall (apple-equivalent)

    def __post_init__(self) -> None:
        _require_positive(self, "width")
        _require_non_negative(self, "max_drain")


@dataclass(frozen=True)
class AgentConfig:
    """Physical and metabolic parameters of an agent."""

    radius: float
    max_speed: float
    initial_energy: float
    max_energy: float
    energy_drain_per_tick: float
    max_age: int
    reproduction_threshold: float
    reproduction_cost: float
    end_of_life_ticks: int
    max_turn_rate: float  # radians/tick for egocentric heading control

    def __post_init__(self) -> None:
        _require_positive(
            self,
            "radius",
            "max_speed",
            "initial_energy",
            "max_energy",
            "max_age",
            "reproduction_threshold",
            "reproduction_cost",
            "end_of_life_ticks",
            "max_turn_rate",
        )
        _require_non_negative(self, "energy_drain_per_tick")


@dataclass(frozen=True)
class SensorConfig:
    """Raycasting sensor layout."""

    num_rays: int
    max_distance: float
    fov: float  # field of view, in degrees

    def __post_init__(self) -> None:
        _require_positive(self, "num_rays", "max_distance", "fov")


@dataclass(frozen=True)
class NetworkConfig:
    """Neural network shape and activation."""

    num_inputs: int
    num_outputs: int
    activation: str

    def __post_init__(self) -> None:
        _require_positive(self, "num_inputs", "num_outputs")
        if not self.activation:
            raise ConfigError("network.activation must be a non-empty string")


@dataclass(frozen=True)
class AppleConfig:
    """Food source parameters."""

    count: int
    radius: float
    energy: float
    respawn_delay: int  # ticks before an eaten apple reappears (invariant n°2)

    def __post_init__(self) -> None:
        _require_positive(self, "count", "radius", "energy", "respawn_delay")


@dataclass(frozen=True)
class GenomeConfig:
    """Mutation operator rates and weight initialisation."""

    weight_init_range: float
    weight_mutation_rate: float
    weight_perturbation: float
    add_node_rate: float
    add_connection_rate: float
    remove_node_rate: float
    remove_connection_rate: float
    weight_max: float  # hard clamp applied after every weight perturbation

    def __post_init__(self) -> None:
        _require_positive(self, "weight_init_range", "weight_perturbation")
        _require_positive(self, "weight_max")
        _require_rate(
            self,
            "weight_mutation_rate",
            "add_node_rate",
            "add_connection_rate",
            "remove_node_rate",
            "remove_connection_rate",
        )


@dataclass(frozen=True)
class SpeciationConfig:
    """Coefficients for the NEAT compatibility-distance diversity metrics.

    Used only by ``src.speciation`` to *observe* the population (species count,
    genetic diversity); these values never influence selection or reproduction.
    Defaults follow the canonical NEAT paper (Stanley & Miikkulainen 2002).
    """

    c_excess: float  # weight of excess genes in the distance
    c_disjoint: float  # weight of disjoint genes in the distance
    c_weight: float  # weight of the mean matching-weight difference
    compatibility_threshold: float  # distance below which two genomes share a species

    def __post_init__(self) -> None:
        _require_positive(self, "compatibility_threshold")
        _require_non_negative(self, "c_excess", "c_disjoint", "c_weight")


@dataclass(frozen=True)
class PopulationConfig:
    """Population bounds."""

    initial_size: int
    min_size: int
    max_size: int

    def __post_init__(self) -> None:
        _require_positive(self, "initial_size", "min_size", "max_size")


@dataclass(frozen=True)
class SimulationConfig:
    """Time stepping and determinism."""

    ticks_per_second: int
    max_ticks: int  # 0 == run forever
    seed: int

    def __post_init__(self) -> None:
        _require_positive(self, "ticks_per_second")
        _require_non_negative(self, "max_ticks")


@dataclass(frozen=True)
class LoggingConfig:
    """Output paths and cadence for metrics and best-genome dumps."""

    csv_path: str
    log_interval_ticks: int
    best_genome_path: str

    def __post_init__(self) -> None:
        _require_positive(self, "log_interval_ticks")
        if not self.csv_path:
            raise ConfigError("logging.csv_path must be a non-empty string")
        if not self.best_genome_path:
            raise ConfigError("logging.best_genome_path must be a non-empty string")


@dataclass(frozen=True)
class RenderConfig:
    """Renderer window and frame rate."""

    fps: int
    window_width: int
    window_height: int

    def __post_init__(self) -> None:
        _require_positive(self, "fps", "window_width", "window_height")


@dataclass(frozen=True)
class SimConfig:
    """Root configuration aggregating every domain section."""

    world: WorldConfig
    penalty_zone: PenaltyZoneConfig
    agent: AgentConfig
    sensors: SensorConfig
    network: NetworkConfig
    apple: AppleConfig
    genome: GenomeConfig
    speciation: SpeciationConfig
    population: PopulationConfig
    simulation: SimulationConfig
    logging: LoggingConfig
    render: RenderConfig

    def __post_init__(self) -> None:
        # Cross-section invariants.
        expected_inputs = 3 * self.sensors.num_rays + 1
        if self.network.num_inputs != expected_inputs:
            raise ConfigError(
                f"network.num_inputs ({self.network.num_inputs}) must equal "
                f"3 * sensors.num_rays + 1 ({expected_inputs})"
            )
        if self.network.num_outputs != 2:
            raise ConfigError(
                f"network.num_outputs must be 2, got {self.network.num_outputs}"
            )
        if self.penalty_zone.width >= min(self.world.width, self.world.height) / 2:
            raise ConfigError(
                "penalty_zone.width must be smaller than half the smallest world "
                "dimension to leave a safe zone"
            )
        if self.agent.reproduction_cost > self.agent.reproduction_threshold:
            raise ConfigError(
                "agent.reproduction_cost must be <= agent.reproduction_threshold"
            )
        if self.agent.max_energy < self.agent.initial_energy:
            raise ConfigError("agent.max_energy must be >= agent.initial_energy")
        if not (
            self.population.min_size
            <= self.population.initial_size
            <= self.population.max_size
        ):
            raise ConfigError(
                "population sizes must satisfy min_size <= initial_size <= max_size"
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SimConfig":
        """Build a ``SimConfig`` from an already-parsed mapping."""
        if not isinstance(data, dict):
            raise ConfigError("configuration root must be a mapping")
        return cls(
            world=_build(WorldConfig, "world", data),
            penalty_zone=_build(PenaltyZoneConfig, "penalty_zone", data),
            agent=_build(AgentConfig, "agent", data),
            sensors=_build(SensorConfig, "sensors", data),
            network=_build(NetworkConfig, "network", data),
            apple=_build(AppleConfig, "apple", data),
            genome=_build(GenomeConfig, "genome", data),
            speciation=_build(SpeciationConfig, "speciation", data),
            population=_build(PopulationConfig, "population", data),
            simulation=_build(SimulationConfig, "simulation", data),
            logging=_build(LoggingConfig, "logging", data),
            render=_build(RenderConfig, "render", data),
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "SimConfig":
        """Load and validate configuration from a YAML file."""
        path = Path(path)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigError(f"cannot read config file '{path}': {exc}") from exc
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ConfigError(f"invalid YAML in '{path}': {exc}") from exc
        return cls.from_dict(data)


def _build(cls: type, section: str, data: dict[str, Any]) -> Any:
    """Instantiate a section dataclass, raising clear ``ConfigError``s."""
    if section not in data:
        raise ConfigError(f"missing config section '{section}'")
    payload = data[section]
    if not isinstance(payload, dict):
        raise ConfigError(f"config section '{section}' must be a mapping")

    allowed = {f.name for f in fields(cls)}
    unknown = set(payload) - allowed
    if unknown:
        raise ConfigError(f"unknown key(s) {sorted(unknown)} in section '{section}'")
    missing = allowed - set(payload)
    if missing:
        raise ConfigError(f"missing key(s) {sorted(missing)} in section '{section}'")
    try:
        return cls(**payload)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"invalid section '{section}': {exc}") from exc


def _require_positive(obj: Any, *names: str) -> None:
    for name in names:
        value = getattr(obj, name)
        if value <= 0:
            raise ConfigError(f"{type(obj).__name__}.{name} must be > 0, got {value}")


def _require_non_negative(obj: Any, *names: str) -> None:
    for name in names:
        value = getattr(obj, name)
        if value < 0:
            raise ConfigError(f"{type(obj).__name__}.{name} must be >= 0, got {value}")


def _require_rate(obj: Any, *names: str) -> None:
    for name in names:
        value = getattr(obj, name)
        if not 0.0 <= value <= 1.0:
            raise ConfigError(
                f"{type(obj).__name__}.{name} must be in [0, 1], got {value}"
            )
