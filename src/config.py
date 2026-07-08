"""Typed, immutable simulation configuration loaded from YAML.

Every tunable parameter in the project lives here and is read through a
``SimConfig`` instance (invariant n°1: no magic numbers in code). The config
is split into one frozen dataclass per domain, mapped 1:1 onto the sections of
``config/default.yaml``.
"""

from __future__ import annotations

from dataclasses import MISSING, dataclass, fields
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
    move_cost: float  # energy/tick per unit forward speed (0.0 = free movement)
    # Structural selection: apples of "reproduction credit" spent per offspring.
    # 0.0 disables it -> legacy energy-threshold reproduction. When > 0, fecundity
    # scales with CUMULATIVE apples eaten (competence), not instantaneous energy.
    apples_per_offspring: float

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
        _require_non_negative(
            self, "energy_drain_per_tick", "move_cost", "apples_per_offspring"
        )


@dataclass(frozen=True)
class SensorConfig:
    """Raycasting sensor layout.

    The per-ray and scalar channels are toggleable so the input representation
    can be ablated without touching code (invariant n°1). Defaults reproduce the
    canonical 67-input layout (poc2.3). Turning all three off yields the legacy
    49-input layout (poc2.2 ``apple_repro_bigpop``): a single combined
    nearest-object distance per ray, two flags, plus energy.
    """

    num_rays: int
    max_distance: float
    fov: float  # field of view, in degrees
    # Per-ray: True → separate apple_dist + wall_dist (2 channels); False → a
    # single combined nearest-object distance (1 channel).
    split_distance: bool = True
    proprioception: bool = True  # append actual_speed scalar
    apples_in_view: bool = True  # append fraction-of-rays-seeing-apple scalar

    def __post_init__(self) -> None:
        _require_positive(self, "num_rays", "max_distance", "fov")

    @property
    def num_inputs(self) -> int:
        """NN input count derived from the enabled channels (no magic number)."""
        per_ray = (2 if self.split_distance else 1) + 2  # distances + 2 flags
        scalars = 1 + int(self.proprioception) + int(self.apples_in_view)  # energy +
        return self.num_rays * per_ray + scalars


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
    crossover_rate: float = 0.0  # P(birth is sexual); 0.0 = legacy asexual cloning
    # Fraction of the full input×output bipartite graph wired at genesis.
    # 1.0 (default) = legacy fully-connected founder (every input -> every
    # output). Lower values start each output with a random SPARSE subset of
    # inputs (at least one, so no output is permanently silent) — reduces the
    # initial weight-vector size independently of num_inputs, so a rich sensor
    # layout need not mean a large mutation surface at birth (audit poc2.3
    # volet 5: initial connectivity, not input count, drove instability).
    initial_connectivity: float = 1.0

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
            "crossover_rate",
            "initial_connectivity",
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
        expected_inputs = self.sensors.num_inputs
        if self.network.num_inputs != expected_inputs:
            raise ConfigError(
                f"network.num_inputs ({self.network.num_inputs}) must equal the "
                f"count derived from the sensor layout ({expected_inputs})"
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
    # Fields carrying a default may be omitted (backward-compatible additions);
    # only fields without any default are mandatory.
    required = {
        f.name
        for f in fields(cls)
        if f.default is MISSING and f.default_factory is MISSING
    }
    missing = required - set(payload)
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
