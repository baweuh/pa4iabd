// ═══════════════════════════════════════════════════════════════════
//  simulation.ts — Fixed-timestep driver (headless, no rendering)
//
//  Base: Python simulation.py (staged pipeline, structural reproduction)
//  Invariant n°7: simulation never touches the renderer.
//
//  Per-tick orchestration:
//    1. Perception + action + eating  (per living agent)
//    2. Metabolism + death marking     (per living agent)
//    3. Deferred apple respawns        (Environment.tickRespawns)
//    4. Reproduction                   (capped at population.max_size)
//    5. Record check + elite injection
//    6. Tick counter + periodic CSV
// ═══════════════════════════════════════════════════════════════════

import type { SimConfig } from './config';
import { TRACKER, Genome, SeededRNG } from './genome';
import { Environment } from './environment';
import { Agent } from './agent';
import { countSpecies, meanPairwiseDistance } from './speciation';

// ── Public snapshot for renderer ────────────────────────────

export interface SimState {
  tick: number;
  population: number;
  foodAvailable: number;
  recordApples: number;
  avgLifespan: number;
  totalReproductions: number;
  avgNetworkSize: number;
  maxGeneration: number;
  meanGeneration: number;
  speciesCount: number;
  meanGeneticDistance: number;
  meanForageRate: number;
  maxForageRate: number;
  isExtinct: boolean;
}

// ── CSV columns ─────────────────────────────────────────────

const CSV_HEADER = [
  'tick', 'population', 'food_available', 'record_apples',
  'avg_lifespan', 'total_reproductions', 'avg_network_size',
  'max_generation', 'mean_generation', 'species_count',
  'mean_genetic_distance', 'mean_forage_rate', 'max_forage_rate',
];

// ── Simulation ──────────────────────────────────────────────

export class Simulation {
  readonly config: SimConfig;
  readonly env: Environment;
  population: Agent[] = [];
  tickCount = 0;
  totalReproductions = 0;
  recordApples = 0;

  private readonly _rng: SeededRNG;
  private readonly _applesEaten = new Map<Agent, number>();
  private readonly _reproCredit = new Map<Agent, number>();
  private readonly _csvLines: string[] = [];
  private _bestGenomeSnapshots: string[] = [];
  private _lastSpeciesCount = 0;
  private _lastMeanDistance = 0;

  constructor(config: SimConfig, rng?: SeededRNG) {
    this.config = config;
    this._rng = rng ?? new SeededRNG(config.simulation.seed);

    // Fresh innovation history per simulation (determinism)
    TRACKER.reset();

    this.env = new Environment(config, this._rng);

    // Spawn initial population
    for (let i = 0; i < config.population.initial_size; i++) {
      const agent = this._spawnAgent();
      this.population.push(agent);
      this._applesEaten.set(agent, 0);
      this._reproCredit.set(agent, 0);
    }
  }

  // ── Population helpers ────────────────────────────────────

  private _spawnAgent(): Agent {
    const genome = Genome.newFullyConnected(
      this.config.network.num_inputs,
      this.config.network.num_outputs,
      this.config.genome,
      this.config.sensors,
      this._rng,
    );
    const [x, y] = this._safeSpawnPosition();
    return new Agent(genome, x, y, this.config, this.env, this._rng);
  }

  private _safeSpawnPosition(): [number, number] {
    const zw = this.config.penalty_zone.width;
    const r = this.config.agent.radius;
    return [
      this._rng.uniform(zw + r, this.config.world.width - zw - r),
      this._rng.uniform(zw + r, this.config.world.height - zw - r),
    ];
  }

  // ── The loop ──────────────────────────────────────────────

  tick(): void {
    // Stage 1 — perception, action, eating
    for (const agent of this.population) {
      agent.age++;
      const [vx, vy] = agent.activate();
      agent.move(vx, vy);
      const eaten = agent.eat();
      const prevEaten = this._applesEaten.get(agent) || 0;
      this._applesEaten.set(agent, prevEaten + eaten);
      const prevCredit = this._reproCredit.get(agent) || 0;
      this._reproCredit.set(agent, prevCredit + eaten);
    }

    // Stage 2 — metabolism and death marking
    for (const agent of this.population) {
      agent.metabolize();
      if (agent.isDead()) {
        agent.alive = false;
      }
    }

    // Stage 3 — deferred apple respawns
    this.env.tickRespawns(this._rng);

    // Stage 4 — reproduction
    const survivors = this.population.filter(a => a.alive);
    const slots = this.config.population.max_size - survivors.length;
    const children: Agent[] = [];

    if (slots > 0) {
      const perChild = this.config.agent.apples_per_offspring;
      if (perChild > 0) {
        this._reproduceByForaging(survivors, slots, perChild, children);
      } else {
        this._reproduceByEnergy(survivors, slots, children);
      }
    }

    // Clean dead agents from bookkeeping
    for (const agent of this.population) {
      if (!agent.alive) {
        this._applesEaten.delete(agent);
        this._reproCredit.delete(agent);
      }
    }

    // Recompose population: survivors + children
    this.population = survivors.concat(children);

    // Stage 5 — record check + elite injection
    this._updateRecord();

    // Stage 6 — tick counter + periodic CSV + incremental metrics
    this.tickCount++;
    this._updateMetrics();
    if (this.tickCount % this.config.simulation.log_interval_ticks === 0) {
      this._logRow();
    }
  }

  // ── Reproduction strategies ───────────────────────────────

  /** Legacy: energy-threshold eligibility, priority by energy (stable sort) */
  private _reproduceByEnergy(survivors: Agent[], slots: number, children: Agent[]): void {
    const eligible = survivors
      .filter(a => a.canReproduce())
      .sort((a, b) => b.energy - a.energy);

    for (const agent of eligible) {
      while (agent.canReproduce() && children.length < slots) {
        children.push(this._birth(agent));
      }
      if (children.length >= slots) break;
    }
  }

  /**
   * Structural reproduction: fecundity driven by CUMULATIVE foraging (Python discovery).
   * Each apple eaten banks +1 credit; spend `perChild` credit per offspring.
   * Parent still pays reproduction_cost energy per child.
   */
  private _reproduceByForaging(survivors: Agent[], slots: number, perChild: number, children: Agent[]): void {
    const eligible = survivors
      .filter(a => (this._reproCredit.get(a) || 0) >= perChild)
      .sort((a, b) => (this._reproCredit.get(b) || 0) - (this._reproCredit.get(a) || 0));

    for (const agent of eligible) {
      while (
        (this._reproCredit.get(agent) || 0) >= perChild
        && agent.energy > 0
        && children.length < slots
      ) {
        this._reproCredit.set(agent, (this._reproCredit.get(agent) || 0) - perChild);
        children.push(this._birth(agent));
      }
      if (children.length >= slots) break;
    }
  }

  private _birth(parent: Agent): Agent {
    const child = parent.reproduce();
    this._applesEaten.set(child, 0);
    this._reproCredit.set(child, 0);
    this.totalReproductions++;
    return child;
  }

  // ── Record / elite injection ──────────────────────────────

  private _updateRecord(): void {
    if (this._applesEaten.size === 0) return;

    let bestAgent: Agent | null = null;
    let bestCount = 0;
    for (const [agent, count] of this._applesEaten) {
      if (count > bestCount) {
        bestCount = count;
        bestAgent = agent;
      }
    }

    if (bestCount > this.recordApples && bestAgent) {
      this.recordApples = bestCount;
      this._saveBestGenome(bestAgent.genome);
      this._injectElite(bestAgent.genome);
    }
  }

  private _injectElite(genome: Genome): void {
    if (this.population.length >= this.config.population.max_size) return;
    const elite = new Agent(
      genome.clone(),
      ...this._safeSpawnPosition(),
      this.config, this.env, this._rng,
    );
    this.population.push(elite);
    this._applesEaten.set(elite, 0);
    this._reproCredit.set(elite, 0);
  }

  private _saveBestGenome(genome: Genome): void {
    this._bestGenomeSnapshots.push(genome.toJSON());
  }

  // ── Metrics ───────────────────────────────────────────────

  get isExtinct(): boolean {
    return this.population.length === 0;
  }

  get foodAvailable(): number {
    return this.env.apples.length;
  }

  // Cached forage rates (computed during _logRow only)
  private _meanForageRate = 0;
  private _maxForageRate = 0;

  // ── CSV ───────────────────────────────────────────────────

  private _logRow(): void {
    const pop = this.population;
    const n = pop.length;

    // Forage rates (only here, not every getState)
    let sumForage = 0;
    let maxForage = 0;
    for (let i = 0; i < n; i++) {
      const eaten = this._applesEaten.get(pop[i]) || 0;
      const rate = eaten / Math.max(pop[i].age, 1);
      sumForage += rate;
      if (rate > maxForage) maxForage = rate;
    }
    this._meanForageRate = n > 0 ? sumForage / n : 0;
    this._maxForageRate = maxForage;

    // Cache speciation (O(n²) — only every log_interval_ticks)
    const genomes = pop.map(a => a.genome);
    this._lastSpeciesCount = countSpecies(genomes, this.config.speciation);
    this._lastMeanDistance = meanPairwiseDistance(genomes, this.config.speciation);

    const row = [
      this.tickCount,
      n,
      this.env.apples.length,
      this.recordApples,
      (n > 0 ? this._sumAge / n : 0).toFixed(6),
      this.totalReproductions,
      (n > 0 ? this._sumNetSize / n : 0).toFixed(6),
      this._maxGen,
      (n > 0 ? this._sumGen / n : 0).toFixed(6),
      this._lastSpeciesCount,
      this._lastMeanDistance.toFixed(6),
      this._meanForageRate.toFixed(6),
      this._maxForageRate.toFixed(6),
    ];

    this._csvLines.push(row.join(','));
  }

  getCsvContent(): string {
    return [CSV_HEADER.join(','), ...this._csvLines].join('\n');
  }

  getBestGenomeSnapshots(): string[] {
    return this._bestGenomeSnapshots;
  }

  // ── Incremental metrics (updated in tick() hot path) ───
  private _maxGen = 0;
  private _sumGen = 0;
  private _sumAge = 0;
  private _sumNetSize = 0;

  /** Call once per tick after population is recomposed. O(n) incremental. */
  private _updateMetrics(): void {
    const pop = this.population;
    const n = pop.length;
    let maxGen = 0;
    let sumGen = 0;
    let sumAge = 0;
    let sumNetSize = 0;
    for (let i = 0; i < n; i++) {
      const a = pop[i];
      if (a.generation > maxGen) maxGen = a.generation;
      sumGen += a.generation;
      sumAge += a.age;
      sumNetSize += a.genome.nodes.length + a.genome.connections.filter(c => c.enabled).length;
    }
    this._maxGen = maxGen;
    this._sumGen = sumGen;
    this._sumAge = sumAge;
    this._sumNetSize = sumNetSize;
  }

  // ── Public snapshot for renderer (O(1) — no iteration) ───

  getState(): SimState {
    const n = this.population.length;
    return {
      tick: this.tickCount,
      population: n,
      foodAvailable: this.env.apples.length,
      recordApples: this.recordApples,
      avgLifespan: n > 0 ? this._sumAge / n : 0,
      totalReproductions: this.totalReproductions,
      avgNetworkSize: n > 0 ? this._sumNetSize / n : 0,
      maxGeneration: this._maxGen,
      meanGeneration: n > 0 ? this._sumGen / n : 0,
      speciesCount: this._lastSpeciesCount,
      meanGeneticDistance: this._lastMeanDistance,
      meanForageRate: n > 0 ? this._meanForageRate : 0,
      maxForageRate: this._maxForageRate,
      isExtinct: this.isExtinct,
    };
  }
}