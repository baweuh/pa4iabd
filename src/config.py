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
    # Minimal-criterion reproduction (Soros & Stanley 2016; non-episodic
    # neuroevolution, e.g. arXiv:2302.09334). Only meaningful on the foraging
    # path (apples_per_offspring > 0). An agent may reproduce only once it has
    # HELD reproduction credit >= apples_per_offspring for this many CONSECUTIVE
    # ticks — proof of durably sustained foraging competence, not an
    # instantaneous spike. When it fires the agent produces exactly ONE
    # offspring and its streak resets (a natural refractory period, so
    # reproduction is no longer a per-tick refill of whatever just died). 0 =
    # legacy behaviour (no sustain requirement, greedy slot-filling), so every
    # existing config is byte-for-byte unchanged. Meant to be paired with a
    # raised population.max_size so the population floats in a band below the
    # cap instead of being pinned at it. Never promoted without a validated
    # 6-seed campaign (extinction risk if too strict: births may stop matching
    # old-age deaths).
    reproduction_min_ticks: int = 0
    # Truncation softening (research-roadmap chantier n°2, untested until
    # poc2.4): both reproduction paths sort eligible agents by priority and let
    # the TOP one fill every open slot via a `while` loop before even looking
    # at the runner-up — the literature (Corus et al. 2021) flags this greedy
    # truncation as a mechanical driver of founder effects / diversity loss.
    # 0 = legacy (unbounded, current behaviour, byte-for-byte unchanged). N > 0
    # caps how many children ANY single agent may produce in one tick, forcing
    # slots that would have gone to the top agent to spill to the next eligible
    # agent instead — softer selection pressure, more parents represented per
    # tick. Applies to both _reproduce_by_energy and the legacy
    # (min_ticks == 0) branch of _reproduce_by_foraging; irrelevant once
    # reproduction_min_ticks > 0, since that gate already caps at one child.
    max_children_per_tick: int = 0
    # Truncation softening, take 2: a single-seed sweep of max_children_per_tick
    # (poc2.4, 2026-07-15) showed the flat per-agent cap either does nothing
    # (never binds when few agents compete for slots) or actively hurts
    # (binds too early, artificially throttling growth even absent real
    # competition). This alternative reshapes HOW slots are handed out instead
    # of how many any one agent may take: eligible agents (priority order) are
    # given children breadth-first, one per agent per PASS, looping back for a
    # second pass only once every still-qualifying agent has had its first —
    # so the top-priority agent can never claim a 2nd child before the
    # runner-up gets its 1st, but an agent facing no competition still gets
    # every slot across successive passes (no artificial ceiling). False (0,
    # default) = legacy greedy while-loop, byte-for-byte unchanged. Composes
    # with max_children_per_tick (still caps total per agent across passes,
    # 0 = unbounded). No-op once reproduction_min_ticks > 0 (already 1
    # child/agent/tick).
    reproduction_round_robin: bool = False

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
        if self.reproduction_min_ticks < 0:
            raise ConfigError(
                "agent.reproduction_min_ticks must be >= 0, got "
                f"{self.reproduction_min_ticks}"
            )
        if self.max_children_per_tick < 0:
            raise ConfigError(
                "agent.max_children_per_tick must be >= 0, got "
                f"{self.max_children_per_tick}"
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
    """Neural network shape and activation.

    poc3: the topology is FIXED (no structural mutation) — ``hidden_size``
    (0 by default) controls it: 0 = a single linear layer straight from
    inputs to outputs (the lowest-capacity shape, matching the near-zero
    hidden-node count the previous NEAT encoding averaged after tens of
    thousands of ticks, see docs/DESIGN-poc3-fixed-topology.md); >0 = one
    hidden layer of that size. See :func:`src.genome.network_layer_shapes`.
    """

    num_inputs: int
    num_outputs: int
    activation: str
    hidden_size: int = 0

    def __post_init__(self) -> None:
        _require_positive(self, "num_inputs", "num_outputs")
        _require_non_negative(self, "hidden_size")
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
    """Weight mutation rates and initialisation.

    poc3: the topology is fixed (see :class:`NetworkConfig`), so there is no
    structural mutation left — only weight perturbation and crossover.
    """

    weight_init_range: float
    weight_mutation_rate: float
    weight_perturbation: float
    weight_max: float  # hard clamp applied after every weight perturbation
    crossover_rate: float = 0.0  # P(birth is sexual); 0.0 = legacy asexual cloning

    def __post_init__(self) -> None:
        _require_positive(self, "weight_init_range", "weight_perturbation")
        _require_positive(self, "weight_max")
        _require_rate(self, "weight_mutation_rate", "crossover_rate")


@dataclass(frozen=True)
class SpeciationConfig:
    """Coefficients for the genetic-distance diversity metrics.

    poc3: with a fixed topology, every genome shares the same weight-vector
    layout — there is no more excess/disjoint gene concept (that only made
    sense when genomes could have different connection sets). Distance is a
    plain mean-absolute-weight-difference over the shared vector.
    ``c_weight``/``compatibility_threshold`` feed ``src.speciation`` for both
    the read-only diversity metrics (species count, genetic diversity in the
    CSV) AND, when ``fitness_sharing`` is on, the species-relative
    reproduction priority.
    """

    c_weight: float  # weight of the mean weight-vector difference
    compatibility_threshold: float  # distance below which two genomes share a species
    # NEAT fitness sharing (f'_i = f_i / |species_i|): divides an agent's
    # reproduction priority by its species size before ranking for scarce
    # slots, protecting small/novel species from being crushed by a larger
    # one's raw fitness before they get a chance to improve. False (default)
    # = legacy behaviour, species purely observational (never promoted to
    # default.yaml without a validated 3-seed campaign).
    fitness_sharing: bool = False

    def __post_init__(self) -> None:
        _require_positive(self, "compatibility_threshold")
        _require_non_negative(self, "c_weight")


@dataclass(frozen=True)
class NoveltyConfig:
    """Additive behavioural-novelty bonus on reproduction priority.

    Novelty search (Lehman & Stanley 2011), used here as an ADDITIVE bonus on top
    of raw fitness — never replacing it. Behaviour is characterised by each
    network's turn-response profile (its steering reaction to a lone apple on
    each ray, deterministic and cached per agent). Novelty = mean distance to the
    ``neighbors`` nearest behaviours in the current population; the most novel
    agents get a bounded priority bonus of up to ``weight × mean(raw fitness)``.

    Additive by design: it is the only pattern that has held up on this project
    (reducer mechanisms — crossover, richer sensors, sparse genome, fitness
    sharing — were all falsified). Disabled by default; the whole section may be
    omitted from a config (then off), so every pre-existing config keeps working.
    Never promoted to default.yaml without a validated 3-seed campaign.

    Optional archive (``archive_enabled``): a persistent pool of past
    behaviours (extinct lineages, earlier generations) that agents are also
    measured novel against, not just the current population. Each scored
    survivor is added to it independently with probability ``archive_prob``
    (Lehman & Stanley 2011's random-injection scheme); oldest entries are
    evicted first past ``archive_max_size``. Meant to help seeds where the
    live population converges and stops offering anything novel to steer
    away from. Off by default; needs its own validated campaign.
    """

    enabled: bool = False
    weight: float = 0.0  # bonus scale, in units of mean raw fitness
    neighbors: int = 15  # k for the k-nearest-behaviours novelty
    # Recompute the O(pop²) novelty scores every N reproduction ticks, reusing the
    # cached scores in between (behaviour drifts slowly — a few births/deaths per
    # tick out of hundreds). 1 = exact (recompute every tick); larger amortises the
    # cost with a negligible approximation. Applying the bonus stays per-tick.
    recompute_interval: int = 1
    archive_enabled: bool = False  # persistent behaviour pool (see class docstring)
    archive_prob: float = 0.01  # P(a scored agent is archived), per refresh
    archive_max_size: int = 500  # FIFO cap on the archive

    def __post_init__(self) -> None:
        _require_non_negative(self, "weight")
        if self.neighbors < 1:
            raise ConfigError(f"novelty.neighbors must be >= 1, got {self.neighbors}")
        if self.recompute_interval < 1:
            raise ConfigError(
                "novelty.recompute_interval must be >= 1, got "
                f"{self.recompute_interval}"
            )
        if not 0.0 <= self.archive_prob <= 1.0:
            raise ConfigError(
                f"novelty.archive_prob must be in [0, 1], got {self.archive_prob}"
            )
        if self.archive_max_size < 1:
            raise ConfigError(
                "novelty.archive_max_size must be >= 1, got " f"{self.archive_max_size}"
            )


@dataclass(frozen=True)
class DiagnosticsConfig:
    """Observational instrumentation — CSV-only, never feeds back into the sim.

    Every value here only shapes what gets LOGGED (capture classification,
    local density sampling, effective-population-size window); none of it is
    read by agent decisions, reproduction or mutation — changing this section
    cannot alter simulation outcomes, only what gets measured about them.

    Capture classification (adjacent / directed / undirected) migrates the
    heuristic from ``tools/apple_capture_probe.py`` (2026-07-09) into a
    permanent runtime metric, fixing its known calibration bug along the way
    (docs/RESULTS-density.md): the probe's fixed ``lookback=30`` ticks did not
    scale with ``agent.max_speed``, so its "60% of the gap closed" threshold
    silently got harder to hit once max_speed was halved (poc2.4 density
    lever). The lookback window is now DERIVED (see
    ``src.diagnostics.capture_lookback_ticks``: ``ceil(sensors.max_distance /
    agent.max_speed)``, the ticks needed to cross the whole sensing range once
    at max speed) instead of a fixed magic number — invariant n°1.
    """

    capture_close_mult: float = 1.5  # "adjacent" if already within this × reach
    capture_directed_ratio: float = 0.6  # fraction of the gap that must close
    capture_ahead_degrees: float = 90.0  # forward half-plane, egocentric
    # Local density (agents/apples within this radius), sampled ONLY at
    # capture events — not every tick (O(pop) or O(apples) per capture, not
    # per tick, so the cost scales with how often apples get eaten, not with
    # simulation length).
    local_density_radius: float = 150.0
    # Effective population size (N_e, Crow & Kimura) rolling window, in ticks.
    # APPROXIMATION for this project's overlapping-generation model (no
    # discrete generations): see src.diagnostics.effective_population_size.
    ne_window_ticks: int = 1000
    # steer_score threshold above which an agent counts as a "forager" for
    # forager_pct (CSV) — matches the value tools/campaign.py has used for
    # every verdict table since poc2.4's novelty campaign.
    forager_threshold: float = 0.1

    def __post_init__(self) -> None:
        _require_positive(self, "capture_close_mult", "local_density_radius")
        _require_rate(self, "capture_directed_ratio")
        if not 0.0 < self.capture_ahead_degrees <= 180.0:
            raise ConfigError(
                "diagnostics.capture_ahead_degrees must be in (0, 180], got "
                f"{self.capture_ahead_degrees}"
            )
        if self.ne_window_ticks < 1:
            raise ConfigError(
                f"diagnostics.ne_window_ticks must be >= 1, got {self.ne_window_ticks}"
            )


@dataclass(frozen=True)
class PopulationConfig:
    """Population bounds.

    There is no runtime population floor: extinction is a legitimate ALife
    outcome (the population dies out if it fails to forage). ``initial_size`` is
    the founder pool; ``max_size`` the carrying capacity.
    """

    initial_size: int
    max_size: int
    # Island model (research-roadmap "modèle d'îles", structural alternative to
    # crossover): partitions the population into N quasi-isolated
    # sub-populations, each its own reproduction-slot budget (max_size split as
    # evenly as possible, see Simulation._island_capacities) and its own
    # eligible/priority ranking and mating pool — a dominant lineage in one
    # island cannot drain another island's slots. A few agents per island
    # migrate one step around a fixed ring every migration_interval_ticks,
    # giving bounded gene flow without merging selection pressure (unlike NEAT
    # fitness sharing, falsified 2026-07-09: species churn every tick, moyenne
    # 62->59%). 1 (default) = legacy single population, byte-for-byte
    # unchanged: no partitioning, no migration, zero extra RNG draws.
    num_islands: int = 1
    migration_interval_ticks: int = 500
    migration_count: int = 1

    def __post_init__(self) -> None:
        _require_positive(self, "initial_size", "max_size")
        if self.num_islands < 1:
            raise ConfigError(
                f"population.num_islands must be >= 1, got {self.num_islands}"
            )
        if self.num_islands > self.max_size:
            raise ConfigError(
                "population.num_islands must be <= population.max_size, got "
                f"{self.num_islands} islands for max_size {self.max_size}"
            )
        if self.migration_interval_ticks < 1:
            raise ConfigError(
                "population.migration_interval_ticks must be >= 1, got "
                f"{self.migration_interval_ticks}"
            )
        if self.migration_count < 0:
            raise ConfigError(
                "population.migration_count must be >= 0, got "
                f"{self.migration_count}"
            )


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
    novelty: NoveltyConfig
    diagnostics: DiagnosticsConfig
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
        if self.population.initial_size > self.population.max_size:
            raise ConfigError("population.initial_size must be <= population.max_size")

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
            # Optional section: absent -> novelty disabled (backward-compatible,
            # every pre-novelty config keeps loading unchanged).
            novelty=(
                _build(NoveltyConfig, "novelty", data)
                if "novelty" in data
                else NoveltyConfig()
            ),
            # Optional section: absent -> defaults (backward-compatible, every
            # pre-diagnostics config keeps loading unchanged).
            diagnostics=(
                _build(DiagnosticsConfig, "diagnostics", data)
                if "diagnostics" in data
                else DiagnosticsConfig()
            ),
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
