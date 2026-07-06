// ═══════════════════════════════════════════════════════════
//  simulation.ts — Boucle principale, NEAT sélection, spéciation
//  Porté de src/simulation.py
// ═══════════════════════════════════════════════════════════

import { Genome, InnovationCounter, SeededRNG } from './genome';
import { Agent } from './agent';
import { Environment } from './environment';
import type { SimConfig } from './config';

// ── Species ──────────────────────────────────────────────

class Species {
  id: number;
  representative: Agent;
  members: Agent[] = [];
  bestFitness = 0;
  stagnationCount = 0;
  totalFitness = 0;

  constructor(id: number, representative: Agent) {
    this.id = id;
    this.representative = representative;
  }

  updateStats(): void {
    if (this.members.length === 0) { this.totalFitness = 0; return; }
    this.totalFitness = this.members.reduce((s, a) => s + a.fitness, 0);
    const currentBest = Math.max(...this.members.map(a => a.fitness));
    if (currentBest > this.bestFitness) {
      this.bestFitness = currentBest;
      this.stagnationCount = 0;
    } else {
      this.stagnationCount++;
    }
  }

  get adjustedFitness(): number {
    if (this.members.length === 0) return 0;
    return this.totalFitness / this.members.length;
  }
}

// ── Simulation ───────────────────────────────────────────

export interface SimState {
  currentTick: number;
  population: number;
  foodAvailable: number;
  recordApples: number;
  totalReproductions: number;
  generation: number;
  numSpecies: number;
  avgEnergy: number;
  avgNetSize: number;
  bestAgentFood: number;
  bestAgentEnergy: number;
  bestAgentAge: number;
  bestAgentChildren: number;
  bestAgentNetSize: number;
  running: boolean;
  seed: number;
  ticksPerFrame: number;
  paused: boolean;
}

export class Simulation {
  cfg: SimConfig;
  rng: SeededRNG;
  actualSeed: number;

  numInputs: number;
  numOutputs: number;
  env: Environment;
  agents: Agent[] = [];

  private species: Species[] = [];
  private nextSpeciesId = 0;
  private speciesRefreshInterval = 50;
  private lastSpeciesRefresh = 0;

  currentTick = 0;
  totalReproductions = 0;
  running = true;
  private generation = 0;

  recordApples = 0;
  bestAgent: Agent | null = null;
  private deadLifespans: number[] = [];

  // Exposed for renderer
  ticksPerFrame = 1;
  paused = false;

  constructor(cfg: SimConfig, seed?: number) {
    this.cfg = cfg;
    const configuredSeed = cfg.simulation.seed ?? seed ?? null;
    let actualSeed: number;
    if (configuredSeed !== null) {
      actualSeed = configuredSeed;
    } else {
      // Random seed
      actualSeed = Math.floor(Math.random() * 2147483647);
    }
    this.actualSeed = actualSeed;
    this.rng = new SeededRNG(actualSeed);

    InnovationCounter().reset();

    this.numInputs = cfg.agents.num_rays * 2 + 1; // 33
    this.numOutputs = 2; // vx, vy

    this.env = new Environment(cfg.environment, this.rng);
    this._bootstrapPopulation();
  }

  private _bootstrapPopulation(): void {
    const cfgA = this.cfg.agents;
    const centerX = this.env.width / 2;
    const centerY = this.env.height / 2;
    const spread = Math.min(this.env.safeMaxX, this.env.safeMaxY) / 3;

    for (let i = 0; i < cfgA.initial_population; i++) {
      const genome = new Genome(this.numInputs, this.numOutputs, this.rng);
      const angle = this.rng.uniform(0, 2 * Math.PI);
      const dist = this.rng.uniform(0, spread);
      let x = centerX + dist * Math.cos(angle);
      let y = centerY + dist * Math.sin(angle);
      [x, y] = this.env.clampPosition(x, y, cfgA.agent_radius);

      const agent = new Agent(
        genome, x, y, cfgA.bootstrap_initial_energy,
        cfgA, this.cfg.mutations, this.rng, true,
      );
      this.agents.push(agent);
    }

    if (this.agents.length > 0) this.bestAgent = this.agents[0];
  }

  step(): boolean {
    if (!this.running) return false;

    // Raycasts + forward pass
    for (const agent of this.agents) {
      if (!agent.alive) continue;
      const inputs = agent.computeRaycasts(this.env);
      agent.think(inputs);
    }

    // Move
    for (const agent of this.agents) {
      if (!agent.alive) continue;
      agent.move(this.env);
      agent.tick();
    }

    // Food collision
    this._checkFoodCollision();

    // Energy drain
    for (const agent of this.agents) {
      if (!agent.alive) continue;
      agent.applyEnergyDrain(this.env);
    }

    // Reproduction
    this._checkReproduction();

    // Death
    this._checkDeath();

    // Respawn apples
    this.env.respawnApples(this.currentTick);

    // Species refresh
    if (this.currentTick - this.lastSpeciesRefresh >= this.speciesRefreshInterval) {
      this._refreshSpecies();
      this.lastSpeciesRefresh = this.currentTick;
    }

    this.currentTick++;

    // Critical population → inject random agents
    if (this.agents.length < 5 && this.currentTick > 200) {
      this._injectRandomAgents(5);
    }

    // Extinction
    if (this.agents.length === 0) {
      this.running = false;
      return false;
    }

    return true;
  }

  private _checkFoodCollision(): void {
    if (this.agents.length === 0) return;

    const agentRadius = this.cfg.agents.agent_radius;
    const foodRadius = this.cfg.agents.food_radius;
    const eatDistSq = (agentRadius + foodRadius) ** 2;

    const activeIndices: number[] = [];
    for (let i = 0; i < this.env.apples.length; i++) {
      if (this.env.apples[i].respawn_at_tick < 0) activeIndices.push(i);
    }
    if (activeIndices.length === 0) return;

    for (const agent of this.agents) {
      if (!agent.alive) continue;
      let closestIdx = -1;
      let closestDistSq = Infinity;
      let closestActiveIdx = -1;

      for (let ai = 0; ai < activeIndices.length; ai++) {
        const appleIdx = activeIndices[ai];
        const apple = this.env.apples[appleIdx];
        const dx = agent.x - apple.x;
        const dy = agent.y - apple.y;
        const distSq = dx * dx + dy * dy;
        if (distSq < closestDistSq) {
          closestDistSq = distSq;
          closestIdx = appleIdx;
          closestActiveIdx = ai;
        }
      }

      if (closestIdx >= 0 && closestDistSq <= eatDistSq) {
        agent.eat(this.cfg.environment.food_energy);
        this.env.eatApple(closestIdx, this.currentTick);
        this._updateBestAgent(agent);
        activeIndices.splice(closestActiveIdx, 1);
        if (activeIndices.length === 0) break;
      }
    }
  }

  private _checkReproduction(): void {
    const cfgA = this.cfg.agents;
    const neatCfg = this.cfg.neat;

    if (this.agents.length >= cfgA.max_population) return;
    if (this.currentTick % neatCfg.reproduction_interval !== 0) return;

    const eligible = this.agents.filter(a => a.alive && a.canReproduce(this.currentTick));
    if (eligible.length < 2) return;

    const targetPop = cfgA.max_population;
    const currentPop = this.agents.length;
    const deficit = targetPop - currentPop;
    const numChildren = Math.min(Math.max(1, Math.floor(deficit / 5)), 5);

    eligible.sort((a, b) => b.fitness - a.fitness);

    const newAgents: Agent[] = [];

    for (let c = 0; c < numChildren; c++) {
      if (eligible.length < 2) break;

      const parent1 = this._tournamentSelect(eligible, neatCfg.tournament_size);

      let parent2: Agent;
      if (this.rng.next() < neatCfg.interspecies_mate_rate && eligible.length >= 2) {
        const candidates = eligible.filter(a => a.speciesId !== parent1.speciesId);
        parent2 = candidates.length > 0
          ? this._tournamentSelect(candidates, neatCfg.tournament_size)
          : this._tournamentSelect(eligible, neatCfg.tournament_size);
      } else {
        const sameSpecies = eligible.filter(a => a.speciesId === parent1.speciesId && a !== parent1);
        parent2 = sameSpecies.length > 0
          ? this._tournamentSelect(sameSpecies, Math.max(1, neatCfg.tournament_size - 1))
          : this._tournamentSelect(eligible, neatCfg.tournament_size);
      }

      let childGenome: Genome;
      if (this.rng.next() < neatCfg.crossover_rate && parent1 !== parent2) {
        childGenome = Genome.crossover(parent1.genome, parent2.genome, parent1.fitness, parent2.fitness, neatCfg, this.rng);
        childGenome.mutate(this.cfg.mutations);
      } else {
        childGenome = parent1.genome.deepCopy();
        childGenome.mutate(this.cfg.mutations);
      }

      parent1.energy = cfgA.parent_energy_after_repro;
      parent1.lastReproductionTick = this.currentTick;
      parent1.childrenCount++;

      const [childX, childY] = parent1.findSpawnPosition(this.env, cfgA.spawn_radius_child);
      const child = new Agent(childGenome, childX, childY, cfgA.child_initial_energy, cfgA, this.cfg.mutations, this.rng, false);
      child.speciesId = parent1.speciesId;

      newAgents.push(child);
      this.totalReproductions++;
      this.generation++;
    }

    this.agents.push(...newAgents);
  }

  private _tournamentSelect(candidates: Agent[], k: number): Agent {
    const actualK = Math.min(k, candidates.length);
    if (actualK <= 0) return candidates[0];
    const tournament = this.rng.sample(candidates, actualK);
    return tournament.reduce((best, a) => a.fitness > best.fitness ? a : best, tournament[0]);
  }

  private _refreshSpecies(): void {
    const neatCfg = this.cfg.neat;
    const aliveAgents = this.agents.filter(a => a.alive);

    // Reset species
    for (const sp of this.species) {
      sp.members = [];
      sp.updateStats();
    }

    // Assign agents to species
    for (const agent of aliveAgents) {
      let assigned = false;
      for (const sp of this.species) {
        const dist = agent.genome.compatibilityDistance(sp.representative.genome, neatCfg);
        if (dist < neatCfg.species_threshold) {
          sp.members.push(agent);
          agent.speciesId = sp.id;
          assigned = true;
          break;
        }
      }

      if (!assigned) {
        const newSp = new Species(this.nextSpeciesId++, agent);
        newSp.members.push(agent);
        agent.speciesId = newSp.id;
        this.species.push(newSp);
      }
    }

    // Update representatives
    for (const sp of this.species) {
      if (sp.members.length > 0) {
        sp.representative = sp.members.reduce((best, a) => a.fitness > best.fitness ? a : best, sp.members[0]);
        sp.updateStats();
      }
    }

    // Remove empty/stagnant species
    this.species = this.species.filter(sp => sp.members.length > 0 && sp.stagnationCount < 30);

    // Recovery
    if (this.species.length === 0 && aliveAgents.length > 0) {
      const best = aliveAgents.reduce((b, a) => a.fitness > b.fitness ? a : b, aliveAgents[0]);
      const newSp = new Species(this.nextSpeciesId++, best);
      for (const a of aliveAgents) {
        if (a.genome.compatibilityDistance(best.genome, neatCfg) < neatCfg.species_threshold * 1.5) {
          newSp.members.push(a);
          a.speciesId = newSp.id;
        }
      }
      if (newSp.members.length === 0) {
        newSp.members.push(best);
        best.speciesId = newSp.id;
      }
      this.species.push(newSp);
    }
  }

  private _checkDeath(): void {
    const survivors: Agent[] = [];
    for (const agent of this.agents) {
      if (agent.isDead()) {
        this.deadLifespans.push(agent.age);
      } else {
        survivors.push(agent);
      }
    }
    this.agents = survivors;

    if (!this.bestAgent || !this.bestAgent.alive) {
      if (this.agents.length > 0) {
        this.bestAgent = this.agents.reduce((b, a) => a.fitness > b.fitness ? a : b, this.agents[0]);
      }
    }
  }

  private _updateBestAgent(agent: Agent): void {
    if (agent.foodEaten > this.recordApples) {
      this.recordApples = agent.foodEaten;
      this.bestAgent = agent;
    }
  }

  private _injectRandomAgents(count: number): void {
    const cfgA = this.cfg.agents;
    const centerX = this.env.width / 2;
    const centerY = this.env.height / 2;
    const spread = Math.min(this.env.safeMaxX, this.env.safeMaxY) / 3;

    for (let i = 0; i < count; i++) {
      let childGenome: Genome;
      if (this.bestAgent && this.rng.next() < 0.5) {
        childGenome = this.bestAgent.genome.deepCopy();
      } else {
        childGenome = new Genome(this.numInputs, this.numOutputs, this.rng);
      }

      for (let m = 0; m < 3; m++) childGenome.mutate(this.cfg.mutations);

      const angle = this.rng.uniform(0, 2 * Math.PI);
      const dist = this.rng.uniform(0, spread);
      let x = centerX + dist * Math.cos(angle);
      let y = centerY + dist * Math.sin(angle);
      [x, y] = this.env.clampPosition(x, y, cfgA.agent_radius);

      const agent = new Agent(childGenome, x, y, cfgA.bootstrap_initial_energy, cfgA, this.cfg.mutations, this.rng, false);
      this.agents.push(agent);
    }
  }

  getState(): SimState {
    const avgEnergy = this.agents.length > 0
      ? this.agents.reduce((s, a) => s + a.energy, 0) / this.agents.length : 0;
    const avgNetSize = this.agents.length > 0
      ? this.agents.reduce((s, a) => s + a.network.networkSize, 0) / this.agents.length : 0;

    const best = this.bestAgent;
    return {
      currentTick: this.currentTick,
      population: this.agents.length,
      foodAvailable: this.env.foodAvailable,
      recordApples: this.recordApples,
      totalReproductions: this.totalReproductions,
      generation: this.generation,
      numSpecies: this.species.length,
      avgEnergy: Math.round(avgEnergy * 100) / 100,
      avgNetSize: Math.round(avgNetSize),
      bestAgentFood: best?.foodEaten ?? 0,
      bestAgentEnergy: best ? Math.round(best.energy * 100) / 100 : 0,
      bestAgentAge: best?.age ?? 0,
      bestAgentChildren: best?.childrenCount ?? 0,
      bestAgentNetSize: best?.network.networkSize ?? 0,
      running: this.running,
      seed: this.actualSeed,
      ticksPerFrame: this.ticksPerFrame,
      paused: this.paused,
    };
  }
}