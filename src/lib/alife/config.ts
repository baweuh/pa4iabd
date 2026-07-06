// ═══════════════════════════════════════════════════════════
//  config.ts — Toute la configuration de la simulation ALife
//  Porté de config/default.yaml
// ═══════════════════════════════════════════════════════════

export interface EnvironmentConfig {
  env_width: number;
  env_height: number;
  zone_width: number;
  zone_max_drain: number;
  food_count: number;
  food_respawn_delay: number;
  food_energy: number;
}

export interface AgentsConfig {
  initial_population: number;
  max_population: number;
  max_speed: number;
  base_drain_rate: number;
  bootstrap_initial_energy: number;
  child_initial_energy: number;
  reproduction_threshold: number;
  parent_energy_after_repro: number;
  max_lifespan: number;
  lifespan_warning_ticks: number;
  agent_radius: number;
  food_radius: number;
  ray_max_range: number;
  num_rays: number;
  spawn_radius_child: number;
  max_energy: number;
  reproduction_cooldown: number;
  parent_selection_fraction: number;
}

export interface MutationsConfig {
  mutate_weights_prob: number;
  weight_perturb_prob: number;
  weight_sigma: number;
  weight_reset_prob: number;
  add_connection_prob: number;
  add_node_prob: number;
  remove_connection_prob: number;
  remove_node_prob: number;
}

export interface NeatConfig {
  tournament_size: number;
  species_threshold: number;
  compatibility_excess_coeff: number;
  compatibility_disjoint_coeff: number;
  compatibility_weight_coeff: number;
  crossover_rate: number;
  interspecies_mate_rate: number;
  elite_fraction: number;
  reproduction_interval: number;
}

export interface SimulationConfig {
  tick_rate: number;
  render_fps: number;
  log_interval: number;
  seed: number | null;
  headless: boolean;
}

export interface SimConfig {
  environment: EnvironmentConfig;
  agents: AgentsConfig;
  mutations: MutationsConfig;
  neat: NeatConfig;
  simulation: SimulationConfig;
}

// ── Default config (values from config/default.yaml) ──────────

export const DEFAULT_CONFIG: SimConfig = {
  environment: {
    env_width: 800,
    env_height: 800,
    zone_width: 60,
    zone_max_drain: 0.04,
    food_count: 60,
    food_respawn_delay: 40,
    food_energy: 2.0,
  },
  agents: {
    initial_population: 40,
    max_population: 100,
    max_speed: 2.5,
    base_drain_rate: 0.001,
    bootstrap_initial_energy: 5.0,
    child_initial_energy: 3.0,
    reproduction_threshold: 6.0,
    parent_energy_after_repro: 3.0,
    max_lifespan: 8000,
    lifespan_warning_ticks: 500,
    agent_radius: 8,
    food_radius: 8,
    ray_max_range: 200,
    num_rays: 16,
    spawn_radius_child: 120,
    max_energy: 10.0,
    reproduction_cooldown: 30,
    parent_selection_fraction: 0.5,
  },
  mutations: {
    mutate_weights_prob: 0.90,
    weight_perturb_prob: 0.80,
    weight_sigma: 0.5,
    weight_reset_prob: 0.10,
    add_connection_prob: 0.05,
    add_node_prob: 0.03,
    remove_connection_prob: 0.01,
    remove_node_prob: 0.005,
  },
  neat: {
    tournament_size: 3,
    species_threshold: 4.0,
    compatibility_excess_coeff: 1.0,
    compatibility_disjoint_coeff: 1.0,
    compatibility_weight_coeff: 0.4,
    crossover_rate: 0.75,
    interspecies_mate_rate: 0.10,
    elite_fraction: 0.1,
    reproduction_interval: 5,
  },
  simulation: {
    tick_rate: 60,
    render_fps: 60,
    log_interval: 100,
    seed: null,
    headless: false,
  },
};