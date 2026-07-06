// ═══════════════════════════════════════════════════════════
//  agent.ts — Agent: raycasts 360°, énergie, fitness, mouvement
//  Porté de src/agent.py
// ═══════════════════════════════════════════════════════════

import { Genome, SeededRNG } from './genome';
import { NeuralNetwork } from './network';
import { Environment } from './environment';
import type { AgentsConfig, MutationsConfig } from './config';

export interface RayHit {
  x: number;
  y: number;
  kind: number; // 0 = nothing, 0.5 = food, 1.0 = wall
}

export class Agent {
  genome: Genome;
  network: NeuralNetwork;
  x: number;
  y: number;
  vx = 0;
  vy = 0;
  energy: number;
  cfg: AgentsConfig;
  cfgMut: MutationsConfig;
  rng: SeededRNG;

  age = 0;
  alive = true;
  isBootstrap: boolean;

  foodEaten = 0;
  childrenCount = 0;
  lastReproductionTick = -999;
  speciesId = -1;

  rays: RayHit[] = [];
  inputSize: number;

  constructor(
    genome: Genome,
    x: number,
    y: number,
    energy: number,
    cfgAgents: AgentsConfig,
    cfgMutations: MutationsConfig,
    rng: SeededRNG,
    isBootstrap: boolean,
  ) {
    this.genome = genome;
    this.network = new NeuralNetwork(genome);
    this.x = x;
    this.y = y;
    this.energy = energy;
    this.cfg = cfgAgents;
    this.cfgMut = cfgMutations;
    this.rng = rng;
    this.isBootstrap = isBootstrap;
    this.inputSize = cfgAgents.num_rays * 2 + 1;
  }

  get fitness(): number {
    const foodBonus = this.foodEaten * 100;
    const survivalBonus = this.age * 0.01;
    const efficiencyBonus = Math.max(0, this.energy) * 2;
    return foodBonus + survivalBonus + efficiencyBonus;
  }

  computeRaycasts(env: Environment): number[] {
    const numRays = this.cfg.num_rays;
    const rayRange = this.genome.ray_range;
    const foodRadius = this.cfg.food_radius;
    const inputs = new Float64Array(this.inputSize);
    this.rays = [];
    const step = (2 * Math.PI) / numRays;

    const maxDistSq = (rayRange + foodRadius + 5) ** 2;
    const activeApples = env.apples.filter(
      a => a.respawn_at_tick < 0 && (a.x - this.x) ** 2 + (a.y - this.y) ** 2 <= maxDistSq,
    );

    for (let i = 0; i < numRays; i++) {
      const angle = i * step;
      const dx = Math.cos(angle);
      const dy = Math.sin(angle);

      // Wall intersection
      let wallT = rayRange + 1;
      if (dx < -1e-9) { const t = -this.x / dx; if (t > 0 && t < wallT) wallT = t; }
      if (dx > 1e-9) { const t = (env.width - this.x) / dx; if (t > 0 && t < wallT) wallT = t; }
      if (dy < -1e-9) { const t = -this.y / dy; if (t > 0 && t < wallT) wallT = t; }
      if (dy > 1e-9) { const t = (env.height - this.y) / dy; if (t > 0 && t < wallT) wallT = t; }

      // Food intersection
      let foodT = rayRange + 1;
      let hitFood = false;
      const detectRSq = (foodRadius + 10) ** 2;

      for (const apple of activeApples) {
        const vfx = apple.x - this.x;
        const vfy = apple.y - this.y;
        const proj = vfx * dx + vfy * dy;
        if (proj <= 0 || proj >= Math.min(wallT, foodT)) continue;
        const px = this.x + proj * dx;
        const py = this.y + proj * dy;
        if ((px - apple.x) ** 2 + (py - apple.y) ** 2 <= detectRSq) {
          foodT = proj;
          hitFood = true;
        }
      }

      // Encode inputs
      if (hitFood && foodT < wallT) {
        inputs[i * 2] = foodT / rayRange;
        inputs[i * 2 + 1] = 0.5;
        this.rays.push({ x: this.x + foodT * dx, y: this.y + foodT * dy, kind: 0.5 });
      } else if (wallT <= rayRange) {
        inputs[i * 2] = wallT / rayRange;
        inputs[i * 2 + 1] = 1.0;
        this.rays.push({ x: this.x + wallT * dx, y: this.y + wallT * dy, kind: 1.0 });
      } else {
        inputs[i * 2] = 1.0;
        inputs[i * 2 + 1] = 0.0;
        this.rays.push({ x: this.x + rayRange * dx, y: this.y + rayRange * dy, kind: 0.0 });
      }
    }

    // Energy input
    inputs[numRays * 2] = Math.min(this.energy / this.cfg.max_energy, 1.0);
    return [...inputs];
  }

  think(inputs: number[]): void {
    const outputs = this.network.activate(inputs);
    this.vx = outputs[0];
    this.vy = outputs[1];
  }

  move(env: Environment): void {
    const maxSpeed = this.cfg.max_speed;
    const speed = Math.sqrt(this.vx ** 2 + this.vy ** 2);
    if (speed > maxSpeed) {
      const scale = maxSpeed / speed;
      this.vx *= scale;
      this.vy *= scale;
    }
    const [newX, newY] = env.clampPosition(this.x + this.vx, this.y + this.vy, this.cfg.agent_radius);
    this.x = newX;
    this.y = newY;
  }

  applyEnergyDrain(env: Environment): void {
    const visionCost = this.genome.ray_range / 150;
    let drain = this.cfg.base_drain_rate * visionCost;
    drain += env.wallPenaltyDrain(this.x, this.y);
    this.energy -= drain;
  }

  eat(foodEnergy: number): void {
    this.energy += foodEnergy;
    this.foodEaten++;
  }

  isDead(): boolean {
    return this.energy <= 0 || this.age >= this.cfg.max_lifespan;
  }

  isDying(): boolean {
    return this.age >= this.cfg.max_lifespan - this.cfg.lifespan_warning_ticks;
  }

  canReproduce(currentTick: number): boolean {
    if (this.energy < this.cfg.reproduction_threshold) return false;
    if (currentTick - this.lastReproductionTick < this.cfg.reproduction_cooldown) return false;
    return true;
  }

  findSpawnPosition(env: Environment, spawnRadius: number): [number, number] {
    for (let attempt = 0; attempt < 50; attempt++) {
      const angle = this.rng.uniform(0, 2 * Math.PI);
      const dist = this.rng.uniform(50, spawnRadius);
      const childX = this.x + dist * Math.cos(angle);
      const childY = this.y + dist * Math.sin(angle);
      if (env.isValidSpawn(childX, childY, this.cfg.agent_radius)) {
        return env.clampPosition(childX, childY, this.cfg.agent_radius);
      }
    }
    return [this.x, this.y];
  }

  tick(): void {
    this.age++;
  }
}