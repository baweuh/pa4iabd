// ═══════════════════════════════════════════════════════════════════
//  environment.ts — World geometry, penalty zone, apple management
//
//  Base: Python environment.py
//  Invariant n°6: apples spawn fully inside the safe zone.
//  Deferred respawn: eaten apple leaves for respawn_delay ticks.
// ═══════════════════════════════════════════════════════════════════

import type { SimConfig, AppleConfig } from './config';
import type { SeededRNG } from './genome';

export class Apple {
  x: number;
  y: number;
  respawnTimer: number;

  constructor(x: number, y: number) {
    this.x = x;
    this.y = y;
    this.respawnTimer = 0;
  }
}

export class Environment {
  apples: Apple[] = [];
  private _pending: Apple[] = [];

  private readonly _worldWidth: number;
  private readonly _worldHeight: number;
  private readonly _penaltyWidth: number;
  private readonly _penaltyMaxDrain: number;
  private readonly _appleRadius: number;
  private readonly _appleEnergy: number;
  private readonly _respawnDelay: number;

  // Safe spawn bounds (inset by penalty zone + apple radius)
  private readonly _xMin: number;
  private readonly _xMax: number;
  private readonly _yMin: number;
  private readonly _yMax: number;

  get worldWidth(): number { return this._worldWidth; }
  get worldHeight(): number { return this._worldHeight; }
  get penaltyWidth(): number { return this._penaltyWidth; }
  get penaltyMaxDrain(): number { return this._penaltyMaxDrain; }
  get appleRadius(): number { return this._appleRadius; }
  get appleEnergy(): number { return this._appleEnergy; }

  constructor(config: SimConfig, rng: SeededRNG) {
    const w = config.world;
    const pz = config.penalty_zone;
    const ac = config.apple;

    this._worldWidth = w.width;
    this._worldHeight = w.height;
    this._penaltyWidth = pz.width;
    this._penaltyMaxDrain = pz.max_drain;
    this._appleRadius = ac.radius;
    this._appleEnergy = ac.energy;
    this._respawnDelay = ac.respawn_delay;

    this._xMin = pz.width + ac.radius;
    this._xMax = w.width - pz.width - ac.radius;
    this._yMin = pz.width + ac.radius;
    this._yMax = w.height - pz.width - ac.radius;

    if (this._xMax <= this._xMin || this._yMax <= this._yMin) {
      throw new Error('penalty_zone.width + apple.radius leaves no safe spawn region');
    }

    for (let i = 0; i < ac.count; i++) {
      this.apples.push(new Apple(...this._randomSafePosition(rng)));
    }
  }

  // ── Geometry helpers ─────────────────────────────────────

  distToWall(x: number, y: number): number {
    return Math.min(x, this._worldWidth - x, y, this._worldHeight - y);
  }

  /** Gradient wall penalty (per tick) — invariant n°2 */
  penaltyAt(x: number, y: number): number {
    const dist = this.distToWall(x, y);
    if (dist < this._penaltyWidth) {
      return this._penaltyMaxDrain * (1.0 - dist / this._penaltyWidth);
    }
    return 0.0;
  }

  // ── Apple lifecycle ──────────────────────────────────────

  markEaten(apple: Apple): void {
    const idx = this.apples.indexOf(apple);
    if (idx >= 0) {
      this.apples.splice(idx, 1);
    }
    apple.respawnTimer = this._respawnDelay;
    this._pending.push(apple);
  }

  tickRespawns(rng: SeededRNG): void {
    const stillPending: Apple[] = [];
    for (const apple of this._pending) {
      apple.respawnTimer--;
      if (apple.respawnTimer <= 0) {
        apple.respawnTimer = 0;
        const [nx, ny] = this._randomSafePosition(rng);
        apple.x = nx;
        apple.y = ny;
        this.apples.push(apple);
      } else {
        stillPending.push(apple);
      }
    }
    this._pending = stillPending;
  }

  // ── Private ──────────────────────────────────────────────

  private _randomSafePosition(rng: SeededRNG): [number, number] {
    return [
      rng.uniform(this._xMin, this._xMax),
      rng.uniform(this._yMin, this._yMax),
    ];
  }
}

// ── Geometry pure functions (shared by agent raycasts) ─────

export { clamp, rayAngles } from './geometry';

export function rayWalls(
  px: number, py: number, dx: number, dy: number,
  width: number, height: number,
): number | null {
  let best: number | null = null;
  if (dx > 0) best = closer(best, (width - px) / dx);
  else if (dx < 0) best = closer(best, -px / dx);
  if (dy > 0) best = closer(best, (height - py) / dy);
  else if (dy < 0) best = closer(best, -py / dy);
  return best;
}

export function rayCircle(
  px: number, py: number, dx: number, dy: number,
  cx: number, cy: number, radius: number,
): number | null {
  const fx = px - cx;
  const fy = py - cy;
  const b = 2.0 * (fx * dx + fy * dy);
  const c = fx * fx + fy * fy - radius * radius;
  const disc = b * b - 4.0 * c;
  if (disc < 0) return null;
  const sqrtDisc = Math.sqrt(disc);
  const tNear = (-b - sqrtDisc) / 2.0;
  if (tNear > 0) return tNear;
  const tFar = (-b + sqrtDisc) / 2.0;
  if (tFar > 0) return tFar;
  return null;
}

function closer(current: number | null, candidate: number): number | null {
  if (candidate <= 0) return current;
  if (current === null || candidate < current) return candidate;
  return current;
}