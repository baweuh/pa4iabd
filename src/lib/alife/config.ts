// ═══════════════════════════════════════════════════════════════════
//  config.ts — Frozen simulation configuration (single source of truth)
//
//  Base: Python pa4iabd-poc2.4 (default.yaml, validated 6-seed campaign)
//  + TS innovations: vision dynamics, connection toggle, evolvable ray range
//
//  Invariant n°1: zero magic numbers — every value comes from here.
//  No YAML dual source — this IS the configuration.
//
//  poc2.4 additions (ported from Python):
//    - NoveltyConfig (behavioural-novelty bonus, Lehman & Stanley 2011)
//    - crossover_rate, initial_connectivity, bias_enabled in GenomeConfig
//    - fitness_sharing in SpeciationConfig
//    - reproduction_min_ticks in AgentConfig
//    - split_distance, proprioception, apples_in_view in SensorConfig
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
  // Minimal-criterion reproduction (Soros & Stanley 2016).
  // 0 = legacy (no sustain requirement, greedy slot-filling).
  readonly reproduction_min_ticks: number;
}

export interface SensorConfig {
  readonly num_rays: number;
  readonly max_distance: number;
  readonly fov: number;
  // Sensor layout toggles (poc2.4 — ablation-safe, backward-compatible)
  readonly split_distance: boolean;   // true → separate apple_dist + wall_dist per ray
  readonly proprioception: boolean;   // append actual_speed scalar
  readonly apples_in_view: boolean;   // append fraction-of-rays-seeing-apple scalar
  // Evolvable ray range (TS innovation, Python has fixed max_distance)
  readonly ray_range_init_min: number;
  readonly ray_range_init_max: number;
  readonly ray_range_min: number;
  readonly ray_range_max: number;
  readonly ray_range_mutation_sigma: number;

  /** Derived NN input count based on enabled channels (no magic number). */
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
  // poc2.4 additions
  readonly crossover_rate: number;        // P(birth is sexual); 0.0 = asexual cloning
  readonly initial_connectivity: number;  // fraction of input×output wired at genesis
  readonly bias_enabled: boolean;         // canonical NEAT bias node (always-on)
}

export interface SpeciationConfig {
  readonly c_excess: number;
  readonly c_disjoint: number;
  readonly c_weight: number;
  readonly compatibility_threshold: number;
  // poc2.4: NEAT fitness sharing (f'_i = f_i / |species_i|)
  readonly fitness_sharing: boolean;
}

/** Additive behavioural-novelty bonus on reproduction priority (poc2.4). */
export interface NoveltyConfig {
  readonly enabled: boolean;
  readonly weight: number;           // bonus scale, in units of mean raw fitness
  readonly neighbors: number;        // k for k-nearest-behaviours novelty
  readonly recompute_interval: number; // amortise O(pop²) scoring
  readonly archive_enabled: boolean;  // persistent behaviour pool
  readonly archive_prob: number;      // P(a scored agent is archived)
  readonly archive_max_size: number;  // FIFO cap on the archive
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
  readonly population: PopulationConfig;
  readonly simulation: SimulationConfig;
}

// ═══════════════════════════════════════════════════════════════════
//  num_inputs derivation (mirrors Python SensorConfig.num_inputs)
// ═══════════════════════════════════════════════════════════════════

function deriveNumInputs(s: {
  num_rays: number;
  split_distance: boolean;
  proprioception: boolean;
  apples_in_view: boolean;
}): number {
  const perRay = (s.split_distance ? 2 : 1) + 2; // distances + 2 flags
  const scalars = 1 + (s.proprioception ? 1 : 0) + (s.apples_in_view ? 1 : 0); // energy + opts
  return s.num_rays * perRay + scalars;
}

// ═══════════════════════════════════════════════════════════════════
//  DEFAULT_CONFIG
//
//  Proven base: Python poc2.4 default.yaml (novelty ON, validated 6-seed)
//  + TS innovations: evolvable ray range, phenotypic plasticity,
//    anti-spinning noise, connection toggle, output protection
//
//  World 1200x675 (16:9 browser-friendly), scaled from 3200x1800
// ═══════════════════════════════════════════════════════════════════

const _sensors = {
  num_rays: 16,
  max_distance: 200,
  fov: 360,
  split_distance: false,    // legacy 49-input layout (validated robust)
  proprioception: false,    // legacy
  apples_in_view: false,    // legacy
  ray_range_init_min: 40,
  ray_range_init_max: 150,
  ray_range_min: 20,
  ray_range_max: 200,
  ray_range_mutation_sigma: 15,
  num_inputs: 0, // derived below
} as SensorConfig;

// Derive num_inputs once (invariant: no magic number)
(_sensors as unknown as Record<string, unknown>).num_inputs = deriveNumInputs(_sensors);

export const DEFAULT_CONFIG: SimConfig = Object.freeze({
  world: {
    width: 1200,
    height: 675,
  },

  penalty_zone: {
    width: 75,
    max_drain: 0.003,
  },

  agent: {
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
    apples_per_offspring: 3.0, // structural foraging-coupled fecundity
    reproduction_min_ticks: 0, // 0 = legacy (no sustain requirement)
  },

  sensors: _sensors,

  // Phenotypic plasticity for vision (TS innovation)
  vision: {
    boost_max: 1.5,
    decay_ticks: 400,
    min_multiplier: 0.4,
  },

  network: {
    num_inputs: _sensors.num_inputs, // derived, not hardcoded
    num_outputs: 2,
    activation: 'tanh',
  },

  apple: {
    count: 80,
    radius: 5,
    energy: 0.5,
    respawn_delay: 150,
  },

  genome: {
    weight_init_range: 1.0,
    weight_mutation_rate: 0.15,
    weight_perturbation: 0.05,
    weight_reset_rate: 0.05,
    add_node_rate: 0.03,
    add_connection_rate: 0.05,
    remove_node_rate: 0.01,
    remove_connection_rate: 0.02,
    connection_toggle_rate: 0.02,    // TS innovation
    weight_max: 5.0,
    crossover_rate: 0.0,             // poc2.4: 0.0 = asexual (default)
    initial_connectivity: 1.0,       // poc2.4: 1.0 = fully-connected founder
    bias_enabled: false,             // poc2.4: false = no bias node
  },

  speciation: {
    c_excess: 1.0,
    c_disjoint: 1.0,
    c_weight: 0.4,
    compatibility_threshold: 3.0,
    fitness_sharing: false,          // poc2.4: false = observational only
  },

  // poc2.4: Novelty search — PROMOTED to default (validated +10% foragers)
  novelty: {
    enabled: true,
    weight: 1.0,
    neighbors: 15,
    recompute_interval: 10,          // amortise O(pop²) to near-zero cost
    archive_enabled: false,
    archive_prob: 0.01,
    archive_max_size: 500,
  },

  population: {
    initial_size: 100,
    min_size: 5,
    max_size: 200,
  },

  simulation: {
    ticks_per_second: 60,
    max_ticks: 0,
    seed: 42,
    log_interval_ticks: 100,
  },
});

// ═══════════════════════════════════════════════════════════════════
//  Validation — cross-section invariants (from Python config.py)
// ═══════════════════════════════════════════════════════════════════

export function validateConfig(cfg: SimConfig): void {
  const { agent, sensors, genome, world, penalty_zone, population, speciation, novelty } = cfg;

  // Network inputs must match derived sensor layout
  const expectedInputs = deriveNumInputs(sensors);
  if (cfg.network.num_inputs !== expectedInputs) {
    throw new ConfigError(
      `network.num_inputs (${cfg.network.num_inputs}) must equal derived sensor count (${expectedInputs})`
    );
  }
  if (cfg.network.num_outputs !== 2) {
    throw new ConfigError(`network.num_outputs must be 2, got ${cfg.network.num_outputs}`);
  }

  // Penalty zone must leave a safe area
  if (penalty_zone.width >= Math.min(world.width, world.height) / 2) {
    throw new ConfigError('penalty_zone.width must be < half the smallest world dimension');
  }

  // Reproduction cost must be <= threshold
  if (agent.reproduction_cost > agent.reproduction_threshold) {
    throw new ConfigError('agent.reproduction_cost must be <= agent.reproduction_threshold');
  }

  // Max energy >= initial energy
  if (agent.max_energy < agent.initial_energy) {
    throw new ConfigError('agent.max_energy must be >= agent.initial_energy');
  }

  // Population ordering
  if (!(population.min_size <= population.initial_size && population.initial_size <= population.max_size)) {
    throw new ConfigError('population: min_size <= initial_size <= max_size required');
  }

  // Reproduction min ticks
  if (agent.reproduction_min_ticks < 0) {
    throw new ConfigError('agent.reproduction_min_ticks must be >= 0');
  }

  // Ray range bounds consistency
  if (sensors.ray_range_min >= sensors.ray_range_max) {
    throw new ConfigError('sensors.ray_range_min must be < sensors.ray_range_max');
  }
  if (sensors.ray_range_init_min < sensors.ray_range_min || sensors.ray_range_init_max > sensors.ray_range_max) {
    throw new ConfigError('ray_range init bounds must be within [ray_range_min, ray_range_max]');
  }

  // Vision consistency
  if (cfg.vision.min_multiplier <= 0 || cfg.vision.boost_max <= 0) {
    throw new ConfigError('vision multipliers must be > 0');
  }

  // Speciation
  if (speciation.compatibility_threshold <= 0) {
    throw new ConfigError('speciation.compatibility_threshold must be > 0');
  }

  // Novelty validation
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