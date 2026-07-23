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
//
//  poc2.4 ports:
//    - Novelty search (additive bonus on reproduction priority)
//    - Crossover (intra-species sexual reproduction)
//    - Fitness sharing (f'_i = f_i / |species_i|)
//    - Minimal-criterion reproduction (sustained foraging gate)
// ═══════════════════════════════════════════════════════════════════

import type { SimConfig } from './config';
import { TRACKER, Genome, SeededRNG } from './genome';
import { Environment } from './environment';
import { Agent } from './agent';
import { countSpecies, meanPairwiseDistance, compatibilityDistance, assignSpecies } from './speciation';
import { CPPN_NUM_INPUTS, CPPN_NUM_OUTPUTS } from './hyperneat';
import { behaviorDescriptor, populationNovelty } from './novelty';

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
  // poc2.4: sustained-credit streak for minimal-criterion gate
  private readonly _creditStreak = new Map<Agent, number>();
  private readonly _csvLines: string[] = [];
  private _bestGenomeSnapshots: string[] = [];
  private _lastSpeciesCount = 0;
  private _lastMeanDistance = 0;

  // poc2.4: novelty scoring state
  private _lastNoveltyTick = -1;
  private _noveltyArchive: number[][] = [];

  constructor(config: SimConfig, rng?: SeededRNG) {
    this.config = config;
    this._rng = rng ?? new SeededRNG(config.simulation.seed);

    TRACKER.reset();

    this.env = new Environment(config, this._rng);

    for (let i = 0; i < config.population.initial_size; i++) {
      const agent = this._spawnAgent();
      this.population.push(agent);
      this._applesEaten.set(agent, 0);
      this._reproCredit.set(agent, 0);
      this._creditStreak.set(agent, 0);
    }
  }

  // ── Population helpers ────────────────────────────────────

  private _spawnAgent(): Agent {
    // Under HyperNEAT the genome is a CPPN (6 coords -> 1 weight),
    // NOT the substrate (sensors -> 2 outputs). The substrate is
    // derived at birth inside Agent's constructor.
    const numIn = this.config.hyperneat.enabled ? CPPN_NUM_INPUTS : this.config.network.num_inputs;
    const numOut = this.config.hyperneat.enabled ? CPPN_NUM_OUTPUTS : this.config.network.num_outputs;
    const genome = Genome.newFullyConnected(
      numIn, numOut,
      this.config.genome, this.config.sensors, this._rng,
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
      agent.applesEaten += eaten;
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
        this._creditStreak.delete(agent);
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
    const priority = this._priorityFn(survivors, (a: Agent) => a.energy);
    const eligible = survivors
      .filter(a => a.canReproduce())
      .sort((a, b) => priority(b) - priority(a));

    for (const agent of eligible) {
      while (agent.canReproduce() && children.length < slots) {
        children.push(this._birth(agent, survivors));
      }
      if (children.length >= slots) break;
    }
  }

  /**
   * Structural reproduction: fecundity driven by CUMULATIVE foraging.
   * poc2.4: now uses _priorityFn() for novelty + fitness sharing composition.
   * poc2.4: minimal-criterion gate via _creditStreak.
   */
  private _reproduceByForaging(survivors: Agent[], slots: number, perChild: number, children: Agent[]): void {
    const minTicks = this.config.agent.reproduction_min_ticks;

    // Refresh credit streaks if minimal-criterion gate is active
    if (minTicks > 0) {
      this._refreshCreditStreaks(survivors, perChild);
    }

    const priority = this._priorityFn(survivors, (a: Agent) => this._reproCredit.get(a) || 0);
    const eligible = survivors
      .filter(a => {
        const credit = this._reproCredit.get(a) || 0;
        const streak = this._creditStreak.get(a) || 0;
        return credit >= perChild && streak >= minTicks;
      })
      .sort((a, b) => priority(b) - priority(a));

    for (const agent of eligible) {
      if (children.length >= slots) break;

      if (minTicks > 0) {
        // Minimal-criterion: one child per qualifying agent per tick, then streak resets
        if (agent.energy > 0) {
          this._reproCredit.set(agent, (this._reproCredit.get(agent) || 0) - perChild);
          this._creditStreak.set(agent, 0);
          children.push(this._birth(agent, survivors));
        }
        continue;
      }

      // Legacy: fill as many slots as credit allows
      while (
        (this._reproCredit.get(agent) || 0) >= perChild
        && agent.energy > 0
        && children.length < slots
      ) {
        this._reproCredit.set(agent, (this._reproCredit.get(agent) || 0) - perChild);
        children.push(this._birth(agent, survivors));
      }
    }
  }

  /**
   * poc2.4: Advance each survivor's sustained-credit streak by one tick.
   * The streak counts consecutive ticks with credit >= perChild;
   * resets to 0 the moment credit falls below.
   */
  private _refreshCreditStreaks(survivors: Agent[], perChild: number): void {
    for (const agent of survivors) {
      const credit = this._reproCredit.get(agent) || 0;
      if (credit >= perChild) {
        this._creditStreak.set(agent, (this._creditStreak.get(agent) || 0) + 1);
      } else {
        this._creditStreak.set(agent, 0);
      }
    }
  }

  /**
   * poc2.4: Reproduction-priority function, optionally modified by:
   * - novelty.enabled → additive novelty bonus (never penalising)
   * - speciation.fitness_sharing → divide by species size
   *
   * Both off (default except novelty): returns raw unchanged.
   */
  private _priorityFn(
    survivors: Agent[],
    raw: (a: Agent) => number,
  ): (a: Agent) => number {
    const noveltyOn = this.config.novelty.enabled && this.config.novelty.weight > 0;
    const sharingOn = this.config.speciation.fitness_sharing;

    if (!sharingOn && !noveltyOn) return raw;

    // Build values map
    const values = new Map<Agent, number>();
    for (const agent of survivors) {
      values.set(agent, raw(agent));
    }

    // Fitness sharing: divide each value by its species size
    if (sharingOn) {
      const speciesIds = assignSpecies(
        survivors.map(a => a.genome), this.config.speciation,
      );
      const speciesSizes = new Map<number, number>();
      for (const sid of speciesIds) {
        speciesSizes.set(sid, (speciesSizes.get(sid) || 0) + 1);
      }
      for (let i = 0; i < survivors.length; i++) {
        const sid = speciesIds[i];
        const size = speciesSizes.get(sid) || 1;
        values.set(survivors[i], values.get(survivors[i])! / size);
      }
    }

    // Novelty: additive bounded bonus
    if (noveltyOn && survivors.length > 1) {
      this._addNoveltyBonus(survivors, values);
    }

    return (a: Agent) => values.get(a) ?? 0;
  }

  /**
   * poc2.4: Add bounded behavioural-novelty bonus to values in place.
   * The most novel agent gets up to weight × mean(base value) extra priority.
   * Expensive O(pop²) scoring runs only every recompute_interval ticks.
   */
  private _addNoveltyBonus(survivors: Agent[], values: Map<Agent, number>): void {
    const cfg = this.config.novelty;
    if (
      this._lastNoveltyTick < 0
      || this.tickCount - this._lastNoveltyTick >= cfg.recompute_interval
    ) {
      this._refreshNoveltyScores(survivors);
    }

    const scores = survivors.map(a => a.noveltyScore);
    let low = Infinity, high = -Infinity;
    for (const s of scores) {
      if (s < low) low = s;
      if (s > high) high = s;
    }
    const span = high - low;
    const meanBase = Array.from(values.values()).reduce((a, b) => a + b, 0) / values.size;
    const scale = cfg.weight * meanBase;

    for (let i = 0; i < survivors.length; i++) {
      const normalised = span > 1e-12 ? (scores[i] - low) / span : 0.0;
      values.set(survivors[i], values.get(survivors[i])! + scale * normalised);
    }
  }

  /**
   * poc2.4: Rescore every survivor's raw novelty (mean k-NN behavioural distance).
   * Cached on each agent; reused until the next refresh.
   * With archive_enabled, also maintains a persistent pool of past behaviours.
   */
  private _refreshNoveltyScores(survivors: Agent[]): void {
    const cfg = this.config.novelty;
    const numInputs = this.config.network.num_inputs;
    const descriptors = survivors.map(a => {
      // Under Hebbian, the network changes during life — cache bypass
      // (matches Python: Agent.behavior_descriptor property).
      if (a._plastic || a._cachedDescriptor === null) {
        a._cachedDescriptor = behaviorDescriptor(a.network, this.config.sensors, numInputs);
      }
      return a._cachedDescriptor!;
    });

    const archive = (cfg.archive_enabled && this._noveltyArchive.length > 0)
      ? this._noveltyArchive
      : null;

    const scores = populationNovelty(descriptors, cfg.neighbors, archive);

    for (let i = 0; i < survivors.length; i++) {
      survivors[i].noveltyScore = scores[i];
    }

    // Archive management (random injection, Lehman & Stanley 2011)
    if (cfg.archive_enabled) {
      for (const desc of descriptors) {
        if (this._rng.next() < cfg.archive_prob) {
          this._noveltyArchive.push(desc);
          if (this._noveltyArchive.length > cfg.archive_max_size) {
            this._noveltyArchive.shift(); // FIFO eviction
          }
        }
      }
    }

    this._lastNoveltyTick = this.tickCount;
  }

  /**
   * poc2.4: Pick an intra-species mate for sexual crossover, or null for asexual.
   */
  private _pickMate(parent: Agent, pool: Agent[]): Agent | null {
    const rate = this.config.genome.crossover_rate;
    if (rate <= 0 || pool.length < 2 || this._rng.next() >= rate) return null;

    const mate = pool[this._rng.int(pool.length)];
    if (mate === parent) return null;

    const distance = compatibilityDistance(parent.genome, mate.genome, this.config.speciation);
    if (distance < this.config.speciation.compatibility_threshold) {
      return mate;
    }
    return null;
  }

  private _birth(parent: Agent, pool: Agent[]): Agent {
    // poc2.4: crossover — child genome comes from crossover with probability crossover_rate
    const mate = this._pickMate(parent, pool);
    const childGenome = parent.reproduce(mate);
    const child = new Agent(
      childGenome,
      ...this._safeSpawnPosition(),
      this.config, this.env, this._rng,
      parent.generation + 1,
      parent.heading,
    );
    this._applesEaten.set(child, 0);
    this._reproCredit.set(child, 0);
    this._creditStreak.set(child, 0);
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
    this._creditStreak.set(elite, 0);
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

  private _meanForageRate = 0;
  private _maxForageRate = 0;

  // ── CSV ───────────────────────────────────────────────────

  private _logRow(): void {
    const pop = this.population;
    const n = pop.length;

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