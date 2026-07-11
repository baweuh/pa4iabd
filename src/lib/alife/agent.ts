// ═══════════════════════════════════════════════════════════════════
//  agent.ts — Perception, decision, movement, energy, lifecycle
//
//  Base: Python agent.py (egocentric model, staged pipeline)
//  + TS innovations:
//    - Evolvable ray_range per genome
//    - Phenotypic plasticity (vision boost after eating, decay when starving)
//    - Anti-spinning exploration noise
//    - Move cost (energy per tick per unit forward speed)
//    - Micro-noise fallback (delegated to NeuralNetwork)
//
//  poc2.4 ports:
//    - Sensor layout configurable (split_distance, proprioception, apples_in_view)
//    - Cached behaviour descriptor for novelty search
//    - Crossover-aware reproduce(mate)
//    - Proprioception tracking (_lastActualSpeed)
//
//  Invariants:
//  n°1 — zero magic numbers
//  n°2 — energy is apple-equivalent per tick
//  n°4 — network topo-sorted once at construction
//  n°5 — egocentric outputs: speed + turn rate
// ═══════════════════════════════════════════════════════════════════

import type { SimConfig, VisionConfig, SensorConfig } from './config';
import type { SeededRNG, Genome } from './genome';
import { NeuralNetwork } from './network';
import { Environment, clamp, rayWalls, rayCircle, rayAngles } from './environment';

// Hit type tokens (internal, not NN inputs)
const TYPE_NOTHING = 0.0;
const TYPE_APPLE = 0.5;
const TYPE_WALL = 1.0;

export class Agent {
  genome: Genome;
  network: NeuralNetwork;
  x: number;
  y: number;
  energy: number;
  age = 0;
  alive = true;
  generation: number;
  heading: number;

  // Cached senses for renderer (never recomputed for display)
  lastSenses: number[] | null = null;

  // Last forward speed magnitude (for move_cost billing)
  private _lastSpeed = 0.0;

  // Proprioception: actual normalised displacement from previous tick
  // (poc2.4: exposed for batch_sense / sensor input)
  _lastActualSpeed = 0.0;

  // Vision dynamics (TS innovation: phenotypic plasticity)
  private _ticksSinceLastMeal = 0;
  private _visionMultiplier = 1.0;

  // poc2.4: cached behaviour descriptor for novelty (computed once, for life)
  _cachedDescriptor: number[] | null = null;
  // Raw novelty score (population-derived, refreshed by Simulation)
  noveltyScore = 0.0;

  private readonly _config: SimConfig;
  private readonly _env: Environment;
  private readonly _rng: SeededRNG;

  constructor(
    genome: Genome,
    x: number,
    y: number,
    config: SimConfig,
    environment: Environment,
    rng: SeededRNG,
    generation = 0,
    heading?: number,
  ) {
    this.genome = genome;
    this.x = x;
    this.y = y;
    this._config = config;
    this._env = environment;
    this._rng = rng;
    this.generation = generation;
    this.heading = heading ?? rng.uniform(0, 2 * Math.PI);

    // Invariant n°4: build (and topo-sort) the network ONCE
    this.network = new NeuralNetwork(genome, config.network);

    this.energy = config.agent.initial_energy;
  }

  // ── Effective ray range (evolvable + plasticity) ─────────

  get effectiveRayRange(): number {
    const vc = this._config.vision;
    const sc = this._config.sensors;

    if (this._ticksSinceLastMeal === 0) {
      this._visionMultiplier = vc.boost_max;
    } else if (this._ticksSinceLastMeal >= vc.decay_ticks) {
      this._visionMultiplier = vc.min_multiplier;
    } else {
      const t = this._ticksSinceLastMeal / vc.decay_ticks;
      this._visionMultiplier = vc.boost_max - (vc.boost_max - vc.min_multiplier) * t;
    }

    return clamp(
      this.genome.ray_range * this._visionMultiplier,
      sc.ray_range_min,
      sc.ray_range_max,
    );
  }

  // ── Perception (layout-aware, poc2.4) ──────────────────

  sense(): number[] {
    const sc = this._config.sensors;
    const rayRange = this.effectiveRayRange;
    const angles = rayAngles(sc.num_rays, sc.fov, this.heading);
    const worldW = this._config.world.width;
    const worldH = this._config.world.height;
    const appleR = this._config.apple.radius;

    const appleDists: number[] = [];
    const wallDists: number[] = [];
    const appleFlags: number[] = [];
    const wallFlags: number[] = [];

    for (const angle of angles) {
      const dx = Math.cos(angle);
      const dy = Math.sin(angle);
      const [hitDist, hitType] = this._castRay(dx, dy, rayRange, appleR, worldW, worldH);
      const normDist = hitDist / rayRange;

      if (sc.split_distance) {
        // Separate channels: apple_dist and wall_dist per ray
        if (hitType === TYPE_APPLE) {
          appleDists.push(normDist);
          wallDists.push(1.0);
        } else if (hitType === TYPE_WALL) {
          appleDists.push(1.0);
          wallDists.push(normDist);
        } else {
          appleDists.push(1.0);
          wallDists.push(1.0);
        }
      } else {
        // Legacy: combined nearest-object distance
        appleDists.push(normDist);
      }

      appleFlags.push(hitType === TYPE_APPLE ? 1.0 : 0.0);
      wallFlags.push(hitType === TYPE_WALL ? 1.0 : 0.0);
    }

    const energyNorm = clamp(this.energy / this._config.agent.max_energy, 0, 1);

    // Assemble based on layout toggles
    let inputs: number[];
    if (sc.split_distance) {
      inputs = [...appleDists, ...wallDists, ...appleFlags, ...wallFlags];
    } else {
      inputs = [...appleDists, ...appleFlags, ...wallFlags];
    }
    inputs.push(energyNorm);

    // Optional proprioceptive scalar (poc2.4)
    if (sc.proprioception) {
      inputs.push(this._lastActualSpeed);
    }

    // Optional apples-in-view scalar (poc2.4)
    if (sc.apples_in_view) {
      const totalFlags = appleFlags.reduce((a, b) => a + b, 0);
      inputs.push(totalFlags / sc.num_rays);
    }

    this.lastSenses = inputs;
    return inputs;
  }

  private _castRay(
    dx: number, dy: number, maxDist: number,
    appleR: number, worldW: number, worldH: number,
  ): [number, number] {
    let hitDist = maxDist;
    let hitType = TYPE_NOTHING;

    // Apples: nearest positive ray-circle intersection
    for (const apple of this._env.apples) {
      const t = rayCircle(this.x, this.y, dx, dy, apple.x, apple.y, appleR);
      if (t !== null && t < hitDist) {
        hitDist = t;
        hitType = TYPE_APPLE;
      }
    }

    // Walls: nearest positive ray-box intersection
    const wallT = rayWalls(this.x, this.y, dx, dy, worldW, worldH);
    if (wallT !== null && wallT < hitDist) {
      hitDist = wallT;
      hitType = TYPE_WALL;
    }

    if (hitDist >= maxDist) return [maxDist, TYPE_NOTHING];
    return [hitDist, hitType];
  }

  // ── Decision and movement (atomic in same tick) ──────────

  activate(): [number, number] {
    const senses = this.sense();
    const [raw0, raw1] = this.network.activate(senses, this._rng);

    // Anti-spinning exploration noise (TS innovation)
    const numRays = this._config.sensors.num_rays;
    const appleFlags = senses.slice(numRays, numRays * 2);
    const foodDetection = appleFlags.reduce((a, b) => a + b, 0);
    const noFoodRatio = 1 - foodDetection / numRays;
    const noiseSigma = 0.12 * noFoodRatio;

    const noisySpeed = raw0 + this._rng.gauss(0, noiseSigma);
    const noisyTurn = raw1 + this._rng.gauss(0, noiseSigma);

    // Egocentric output interpretation (invariant n°5)
    const speed = Math.tanh(noisySpeed) * this._config.agent.max_speed;
    this._lastSpeed = Math.abs(speed);
    this.heading = (this.heading + Math.tanh(noisyTurn) * this._config.agent.max_turn_rate) % (2 * Math.PI);
    if (this.heading < 0) this.heading += 2 * Math.PI;

    // World-frame velocity
    const vx = speed * Math.cos(this.heading);
    const vy = speed * Math.sin(this.heading);
    return [vx, vy];
  }

  move(vx: number, vy: number): void {
    const r = this._config.agent.radius;
    const oldX = this.x;
    const oldY = this.y;
    this.x = clamp(this.x + vx, r, this._config.world.width - r);
    this.y = clamp(this.y + vy, r, this._config.world.height - r);
    // poc2.4: track actual normalised displacement for proprioception
    this._lastActualSpeed = Math.hypot(this.x - oldX, this.y - oldY) / this._config.agent.max_speed;
  }

  // ── Energy (per tick — invariant n°2) ────────────────────

  metabolize(): void {
    // Base drain
    this.energy -= this._config.agent.energy_drain_per_tick;
    // Activity cost (move_cost × |forward speed|)
    this.energy -= this._config.agent.move_cost * this._lastSpeed;
    // Gradient wall penalty
    this.energy -= this._env.penaltyAt(this.x, this.y);
    // Cap
    if (this.energy > this._config.agent.max_energy) {
      this.energy = this._config.agent.max_energy;
    }
    // Increment hunger counter (vision dynamics)
    this._ticksSinceLastMeal++;
  }

  eat(): number {
    const reach = this._config.agent.radius + this._config.apple.radius;
    const gain = this._config.apple.energy;
    const bitten: typeof this._env.apples = [];
    for (const apple of this._env.apples) {
      const dx = apple.x - this.x;
      const dy = apple.y - this.y;
      if (Math.sqrt(dx * dx + dy * dy) <= reach) {
        bitten.push(apple);
      }
    }
    for (const apple of bitten) {
      this.energy = Math.min(this.energy + gain, this._config.agent.max_energy);
      this._env.markEaten(apple);
      // Vision dynamics: reset hunger counter → immediate boost
      this._ticksSinceLastMeal = 0;
    }
    return bitten.length;
  }

  // ── Lifecycle ────────────────────────────────────────────

  isDead(): boolean {
    return this.energy <= 0 || this.age >= this._config.agent.max_age;
  }

  isDying(): boolean {
    return this.age >= this._config.agent.max_age - this._config.agent.end_of_life_ticks;
  }

  canReproduce(): boolean {
    return this.energy >= this._config.agent.reproduction_threshold;
  }

  /**
   * Spawn a mutated child. With `mate`, uses crossover (poc2.4).
   * Without mate, asexual clone + mutation (legacy).
   * The child genome is returned (not the Agent — Simulation wraps it).
   */
  reproduce(mate: Agent | null = null): Genome {
    this.energy -= this._config.agent.reproduction_cost;

    let childGenome: Genome;
    if (mate === null) {
      childGenome = this.genome.clone();
    } else {
      childGenome = Genome.crossover(this.genome, mate.genome, this._rng);
    }
    childGenome.mutate(this._config.genome, this._rng);

    return childGenome;
  }
}