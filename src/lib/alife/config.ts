// ═══════════════════════════════════════════════════════════════════
//  config.ts — Frozen simulation configuration (single source of truth)
//
//  Base: Python pa4iabd-poc2.6 (default.yaml)
//  + TS innovations: vision dynamics, connection toggle, evolvable ray range
//
//  Invariant n°1: zero magic numbers — every value comes from here.
//  No YAML dual source — this IS the configuration.
//
//  poc2.4 additions: NoveltyConfig, crossover, initial_connectivity, bias,
//    fitness_sharing, reproduction_min_ticks, sensor toggles
//  poc2.5 additions: HyperNEATConfig (indirect encoding)
//  poc2.6 additions: HebbianConfig (reward-modulated plasticity),
//    DiagnosticsConfig (capture classification, N_e)
// ═══════════════════════════════════════════════════════════════════

export class ConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ConfigError';
  }
}

// ── Frozen section types ──────────────────────────────────────

export interface WorldConfig {
  readonly width: number;
  readonly height: number;
}

export interface PenaltyZoneConfig {
  readonly width: number;
  readonly max_drain: number;
}

export interface AgentConfig {
  readonly radius: number;
  readonly max_speed: number;
  readonly initial_energy: number;
  readonly max_energy: number;
  readonly energy_drain_per_tick: number;
  readonly max_age: number;
  readonly reproduction_threshold: number;
  readonly reproduction_cost: number;
  readonly end_of_life_ticks: number;
  readonly max_turn_rate: number;
  readonly move_cost: number;
  readonly apples_per_offspring: number;
  readonly reproduction_min_ticks: number;
}

export interface SensorConfig {
  readonly num_rays: number;
  readonly max_distance: number;
  readonly fov: number;
  readonly split_distance: boolean;
  readonly proprioception: boolean;
  readonly apples_in_view: boolean;
  // Evolvable ray range (TS innovation)
  readonly ray_range_init_min: number;
  readonly ray_range_init_max: number;
  readonly ray_range_min: number;
  readonly ray_range_max: number;
  readonly ray_range_mutation_sigma: number;
  /** Derived NN input count based on enabled channels. */
  readonly num_inputs: number;
}

export interface VisionConfig {
  readonly boost_max: number;
  readonly decay_ticks: number;
  readonly min_multiplier: number;
}

export interface NetworkConfig {
  readonly num_inputs: number;
  readonly num_outputs: number;
  readonly activation: string;
}

export interface AppleConfig {
  readonly count: number;
  readonly radius: number;
  readonly energy: number;
  readonly respawn_delay: number;
}

export interface GenomeConfig {
  readonly weight_init_range: number;
  readonly weight_mutation_rate: number;
  readonly weight_perturbation: number;
  readonly weight_reset_rate: number;
  readonly add_node_rate: number;
  readonly add_connection_rate: number;
  readonly remove_node_rate: number;
  readonly remove_connection_rate: number;
  readonly connection_toggle_rate: number;
  readonly weight_max: number;
  readonly crossover_rate: number;
  readonly initial_connectivity: number;
  readonly bias_enabled: boolean;
}

export interface SpeciationConfig {
  readonly c_excess: number;
  readonly c_disjoint: number;
  readonly c_weight: number;
  readonly compatibility_threshold: number;
  readonly fitness_sharing: boolean;
}

/** Additive behavioural-novelty bonus on reproduction priority (poc2.4). */
export interface NoveltyConfig {
  readonly enabled: boolean;
  readonly weight: number;
  readonly neighbors: number;
  readonly recompute_interval: number;
  readonly archive_enabled: boolean;
  readonly archive_prob: number;
  readonly archive_max_size: number;
}

/** Observational instrumentation — CSV-only, never feeds back into the sim (poc2.6). */
export interface DiagnosticsConfig {
  readonly capture_close_mult: number;
  readonly capture_directed_ratio: number;
  readonly capture_ahead_degrees: number;
  readonly local_density_radius: number;
  readonly ne_window_ticks: number;
  readonly forager_threshold: number;
}

/** Indirect encoding: genome evolves a CPPN queried over a fixed substrate (poc2.5). */
export interface HyperNEATConfig {
  readonly enabled: boolean;
  readonly weight_scale: number;
  readonly connectivity: number;
  readonly bootstrap_hidden_nodes: number;
}

/** Reward-modulated Hebbian plasticity: agent learns DURING its life (poc2.6). */
export interface HebbianConfig {
  readonly enabled: boolean;
  readonly learning_rate: number;
  readonly weight_max: number;
  readonly eligibility_decay: number;
  readonly baseline_rate: number;
}

export interface PopulationConfig {
  readonly initial_size: number;
  readonly min_size: number;
  readonly max_size: number;
}

export interface SimulationConfig {
  readonly ticks_per_second: number;
  readonly max_ticks: number;
  readonly seed: number;
  readonly log_interval_ticks: number;
}

export interface SimConfig {
  readonly world: WorldConfig;
  readonly penalty_zone: PenaltyZoneConfig;
  readonly agent: AgentConfig;
  readonly sensors: SensorConfig;
  readonly vision: VisionConfig;
  readonly network: NetworkConfig;
  readonly apple: AppleConfig;
  readonly genome: GenomeConfig;
  readonly speciation: SpeciationConfig;
  readonly novelty: NoveltyConfig;
  readonly diagnostics: DiagnosticsConfig;
  readonly hyperneat: HyperNEATConfig;
  readonly hebbian: HebbianConfig;
  readonly population: PopulationConfig;
  readonly simulation: SimulationConfig;
}

// ═══════════════════════════════════════════════════════════════════
//  num_inputs derivation (mirrors Python SensorConfig.num_inputs)
// ═══════════════════════════════════════════════════════════════════

export function deriveNumInputs(s: {
  num_rays: number;
  split_distance: boolean;
  proprioception: boolean;
  apples_in_view: boolean;
}): number {
  const perRay = (s.split_distance ? 2 : 1) + 2;
  const scalars = 1 + (s.proprioception ? 1 : 0) + (s.apples_in_view ? 1 : 0);
  return s.num_rays * perRay + scalars;
}

// ═══════════════════════════════════════════════════════════════════
//  DEFAULT_CONFIG
//
//  Synced from Python poc2.6 default.yaml.
//  World 1200x675 (16:9 browser-friendly), scaled from 3200x1800.
//  apples_per_offspring: 1.5 (poc2.4 K-sweep winner).
//  All new features (hyperneat, hebbian, diagnostics) default to disabled.
// ═══════════════════════════════════════════════════════════════════

const _sensors = {
  num_rays: 16,
  max_distance: 200,
  fov: 360,
  split_distance: false,
  proprioception: false,
  apples_in_view: false,
  ray_range_init_min: 40,
  ray_range_init_max: 150,
  ray_range_min: 20,
  ray_range_max: 200,
  ray_range_mutation_sigma: 15,
  num_inputs: 0,
} as SensorConfig;

(_sensors as unknown as Record<string, unknown>).num_inputs = deriveNumInputs(_sensors);

export const DEFAULT_CONFIG: SimConfig = Object.freeze({
  world: Object.freeze({ width: 1200, height: 675 }),

  penalty_zone: Object.freeze({ width: 75, max_drain: 0.003 }),

  agent: Object.freeze({
    radius: 8,
    max_speed: 3.0,
    initial_energy: 1.0,
    max_energy: 2.0,
    energy_drain_per_tick: 0.0004,
    max_age: 5000,
    reproduction_threshold: 1.1,
    reproduction_cost: 0.35,
    end_of_life_ticks: 500,
    max_turn_rate: 0.2,
    move_cost: 0.0,
    apples_per_offspring: 1.5,  // synced: poc2.4 K-sweep winner
    reproduction_min_ticks: 0,
  }),

  sensors: Object.freeze(_sensors),

  vision: Object.freeze({ boost_max: 1.5, decay_ticks: 400, min_multiplier: 0.4 }),

  network: Object.freeze({
    num_inputs: _sensors.num_inputs,
    num_outputs: 2,
    activation: 'tanh',
  }),

  apple: Object.freeze({ count: 80, radius: 5, energy: 0.5, respawn_delay: 150 }),

  genome: Object.freeze({
    weight_init_range: 1.0,
    weight_mutation_rate: 0.15,
    weight_perturbation: 0.05,
    weight_reset_rate: 0.05,
    add_node_rate: 0.03,
    add_connection_rate: 0.05,
    remove_node_rate: 0.01,
    remove_connection_rate: 0.02,
    connection_toggle_rate: 0.02,
    weight_max: 5.0,
    crossover_rate: 0.0,
    initial_connectivity: 1.0,
    bias_enabled: false,
  }),

  speciation: Object.freeze({
    c_excess: 1.0,
    c_disjoint: 1.0,
    c_weight: 0.4,
    compatibility_threshold: 3.0,
    fitness_sharing: false,
  }),

  novelty: Object.freeze({
    enabled: true,
    weight: 1.0,
    neighbors: 15,
    recompute_interval: 10,
    archive_enabled: false,
    archive_prob: 0.01,
    archive_max_size: 500,
  }),

  // poc2.6: Diagnostics — observational, CSV-only
  diagnostics: Object.freeze({
    capture_close_mult: 1.5,
    capture_directed_ratio: 0.6,
    capture_ahead_degrees: 90.0,
    local_density_radius: 150.0,
    ne_window_ticks: 1000,
    forager_threshold: 0.1,
  }),

  // poc2.5: HyperNEAT — disabled by default
  hyperneat: Object.freeze({
    enabled: false,
    weight_scale: 3.0,
    connectivity: 1.0,
    bootstrap_hidden_nodes: 0,
  }),

  // poc2.6: Hebbian — disabled by default
  hebbian: Object.freeze({
    enabled: false,
    learning_rate: 0.01,
    weight_max: 5.0,
    eligibility_decay: 0.99,
    baseline_rate: 0.01,
  }),

  population: Object.freeze({ initial_size: 100, min_size: 5, max_size: 200 }),

  simulation: Object.freeze({
    ticks_per_second: 60,
    max_ticks: 0,
    seed: 42,
    log_interval_ticks: 100,
  }),
});

// ═══════════════════════════════════════════════════════════════════
//  Validation — cross-section invariants (from Python config.py)
// ═══════════════════════════════════════════════════════════════════

export function validateConfig(cfg: SimConfig): void {
  const { agent, sensors, genome, world, penalty_zone, population, speciation, novelty,
          diagnostics, hyperneat, hebbian } = cfg;

  const expectedInputs = deriveNumInputs(sensors);
  if (cfg.network.num_inputs !== expectedInputs) {
    throw new ConfigError(
      `network.num_inputs (${cfg.network.num_inputs}) must equal derived sensor count (${expectedInputs})`
    );
  }
  if (cfg.network.num_outputs !== 2) {
    throw new ConfigError(`network.num_outputs must be 2, got ${cfg.network.num_outputs}`);
  }
  if (penalty_zone.width >= Math.min(world.width, world.height) / 2) {
    throw new ConfigError('penalty_zone.width must be < half the smallest world dimension');
  }
  if (agent.reproduction_cost > agent.reproduction_threshold) {
    throw new ConfigError('agent.reproduction_cost must be <= agent.reproduction_threshold');
  }
  if (agent.max_energy < agent.initial_energy) {
    throw new ConfigError('agent.max_energy must be >= agent.initial_energy');
  }
  if (!(population.min_size <= population.initial_size && population.initial_size <= population.max_size)) {
    throw new ConfigError('population: min_size <= initial_size <= max_size required');
  }
  if (agent.reproduction_min_ticks < 0) {
    throw new ConfigError('agent.reproduction_min_ticks must be >= 0');
  }
  if (sensors.ray_range_min >= sensors.ray_range_max) {
    throw new ConfigError('sensors.ray_range_min must be < sensors.ray_range_max');
  }
  if (sensors.ray_range_init_min < sensors.ray_range_min || sensors.ray_range_init_max > sensors.ray_range_max) {
    throw new ConfigError('ray_range init bounds must be within [ray_range_min, ray_range_max]');
  }
  if (cfg.vision.min_multiplier <= 0 || cfg.vision.boost_max <= 0) {
    throw new ConfigError('vision multipliers must be > 0');
  }
  if (speciation.compatibility_threshold <= 0) {
    throw new ConfigError('speciation.compatibility_threshold must be > 0');
  }
  if (novelty.neighbors < 1) {
    throw new ConfigError(`novelty.neighbors must be >= 1, got ${novelty.neighbors}`);
  }
  if (novelty.recompute_interval < 1) {
    throw new ConfigError(`novelty.recompute_interval must be >= 1, got ${novelty.recompute_interval}`);
  }
  if (novelty.archive_prob < 0 || novelty.archive_prob > 1) {
    throw new ConfigError(`novelty.archive_prob must be in [0, 1], got ${novelty.archive_prob}`);
  }
  if (novelty.archive_max_size < 1) {
    throw new ConfigError(`novelty.archive_max_size must be >= 1, got ${novelty.archive_max_size}`);
  }

  // Diagnostics validation (poc2.6)
  if (diagnostics.capture_ahead_degrees <= 0 || diagnostics.capture_ahead_degrees > 180) {
    throw new ConfigError(`diagnostics.capture_ahead_degrees must be in (0, 180], got ${diagnostics.capture_ahead_degrees}`);
  }
  if (diagnostics.ne_window_ticks < 1) {
    throw new ConfigError(`diagnostics.ne_window_ticks must be >= 1, got ${diagnostics.ne_window_ticks}`);
  }
  if (diagnostics.capture_directed_ratio < 0 || diagnostics.capture_directed_ratio > 1) {
    throw new ConfigError(`diagnostics.capture_directed_ratio must be in [0, 1], got ${diagnostics.capture_directed_ratio}`);
  }

  // HyperNEAT validation (poc2.5)
  if (hyperneat.weight_scale <= 0) {
    throw new ConfigError(`hyperneat.weight_scale must be > 0, got ${hyperneat.weight_scale}`);
  }
  if (hyperneat.connectivity < 0 || hyperneat.connectivity > 1) {
    throw new ConfigError(`hyperneat.connectivity must be in [0, 1], got ${hyperneat.connectivity}`);
  }
  if (hyperneat.bootstrap_hidden_nodes < 0) {
    throw new ConfigError(`hyperneat.bootstrap_hidden_nodes must be >= 0, got ${hyperneat.bootstrap_hidden_nodes}`);
  }

  // Hebbian validation (poc2.6)
  if (hebbian.learning_rate < 0) {
    throw new ConfigError(`hebbian.learning_rate must be >= 0, got ${hebbian.learning_rate}`);
  }
  if (hebbian.weight_max <= 0) {
    throw new ConfigError(`hebbian.weight_max must be > 0, got ${hebbian.weight_max}`);
  }
  if (hebbian.eligibility_decay < 0 || hebbian.eligibility_decay > 1) {
    throw new ConfigError(`hebbian.eligibility_decay must be in [0, 1], got ${hebbian.eligibility_decay}`);
  }
  if (hebbian.baseline_rate < 0 || hebbian.baseline_rate > 1) {
    throw new ConfigError(`hebbian.baseline_rate must be in [0, 1], got ${hebbian.baseline_rate}`);
  }

  // Rates in [0, 1]
  const rates: [string, number][] = [
    ['genome.weight_mutation_rate', genome.weight_mutation_rate],
    ['genome.add_node_rate', genome.add_node_rate],
    ['genome.add_connection_rate', genome.add_connection_rate],
    ['genome.remove_node_rate', genome.remove_node_rate],
    ['genome.remove_connection_rate', genome.remove_connection_rate],
    ['genome.connection_toggle_rate', genome.connection_toggle_rate],
    ['genome.crossover_rate', genome.crossover_rate],
    ['genome.initial_connectivity', genome.initial_connectivity],
  ];
  for (const [name, val] of rates) {
    if (val < 0 || val > 1) {
      throw new ConfigError(`${name} must be in [0, 1], got ${val}`);
    }
  }
}
