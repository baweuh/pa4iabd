// ═══════════════════════════════════════════════════════════════════
//  config.ts — Frozen simulation configuration (single source of truth)
//
//  Base: Python pa4iabd-poc2.2 (apple_repro_bigpop proven config)
//  + TS innovations: vision dynamics, connection toggle, evolvable ray range
//
//  Invariant n°1: zero magic numbers — every value comes from here.
//  No YAML dual source — this IS the configuration.
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
}

export interface SensorConfig {
  readonly num_rays: number;
  readonly max_distance: number;
  readonly fov: number;
  readonly ray_range_init_min: number;
  readonly ray_range_init_max: number;
  readonly ray_range_min: number;
  readonly ray_range_max: number;
  readonly ray_range_mutation_sigma: number;
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
}

export interface SpeciationConfig {
  readonly c_excess: number;
  readonly c_disjoint: number;
  readonly c_weight: number;
  readonly compatibility_threshold: number;
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
  readonly population: PopulationConfig;
  readonly simulation: SimulationConfig;
}

// ═══════════════════════════════════════════════════════════════════
//  DEFAULT_CONFIG
//
//  Proven base: Python apple_repro_bigpop (structural foraging reproduction)
//  + TS innovations: evolvable ray range, phenotypic plasticity,
//    anti-spinning noise, connection toggle, output protection
//
//  World 1200x675 (16:9 browser-friendly), scaled from 2263x1273
// ═══════════════════════════════════════════════════════════════════

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
  },

  sensors: {
    num_rays: 16,
    max_distance: 200, // global cap (effective range is per-agent, evolvable)
    fov: 360,
    // Evolvable ray range (TS innovation, Python has fixed max_distance)
    ray_range_init_min: 40,
    ray_range_init_max: 150,
    ray_range_min: 20,
    ray_range_max: 200,
    ray_range_mutation_sigma: 15,
  },

  // Phenotypic plasticity for vision (TS innovation)
  vision: {
    boost_max: 1.5,       // ×1.5 range right after eating
    decay_ticks: 400,     // ticks to go from boost to minimum
    min_multiplier: 0.4,  // ×0.4 range when starving
  },

  network: {
    num_inputs: 49, // 3 * 16 rays + 1 energy
    num_outputs: 2, // speed + turn rate (egocentric)
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
    connection_toggle_rate: 0.02, // TS innovation
    weight_max: 5.0,
  },

  speciation: {
    c_excess: 1.0,
    c_disjoint: 1.0,
    c_weight: 0.4,
    compatibility_threshold: 3.0,
  },

  population: {
    initial_size: 100,
    min_size: 5,
    max_size: 200,
  },

  simulation: {
    ticks_per_second: 60,
    max_ticks: 0, // 0 = run forever
    seed: 42,
    log_interval_ticks: 100,
  },
});

// ═══════════════════════════════════════════════════════════════════
//  Validation — cross-section invariants (from Python config.py)
// ═══════════════════════════════════════════════════════════════════

export function validateConfig(cfg: SimConfig): void {
  const { agent, sensors, genome, world, penalty_zone, population, speciation } = cfg;

  // Network inputs must equal 3 * num_rays + 1
  const expectedInputs = 3 * sensors.num_rays + 1;
  if (cfg.network.num_inputs !== expectedInputs) {
    throw new ConfigError(
      `network.num_inputs (${cfg.network.num_inputs}) must equal 3 * sensors.num_rays + 1 (${expectedInputs})`
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

  // Rates in [0, 1]
  const rates: [string, number][] = [
    ['genome.weight_mutation_rate', genome.weight_mutation_rate],
    ['genome.add_node_rate', genome.add_node_rate],
    ['genome.add_connection_rate', genome.add_connection_rate],
    ['genome.remove_node_rate', genome.remove_node_rate],
    ['genome.remove_connection_rate', genome.remove_connection_rate],
    ['genome.connection_toggle_rate', genome.connection_toggle_rate],
  ];
  for (const [name, val] of rates) {
    if (val < 0 || val > 1) {
      throw new ConfigError(`${name} must be in [0, 1], got ${val}`);
    }
  }
}