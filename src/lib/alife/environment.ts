// ═══════════════════════════════════════════════════════════
//  environment.ts — Pommes, zone pénalité, spawn/respawn
//  Porté de src/environment.py
// ═══════════════════════════════════════════════════════════

import { SeededRNG } from './genome';
import type { EnvironmentConfig } from './config';

export interface Apple {
  x: number;
  y: number;
  respawn_at_tick: number; // -1 = active
}

export class Environment {
  cfg: EnvironmentConfig;
  rng: SeededRNG;
  width: number;
  height: number;
  zoneWidth: number;
  zoneMaxDrain: number;
  safeMin: number;
  safeMaxX: number;
  safeMaxY: number;
  apples: Apple[];

  constructor(cfg: EnvironmentConfig, rng: SeededRNG) {
    this.cfg = cfg;
    this.rng = rng;
    this.width = cfg.env_width;
    this.height = cfg.env_height;
    this.zoneWidth = cfg.zone_width;
    this.zoneMaxDrain = cfg.zone_max_drain;
    this.safeMin = this.zoneWidth;
    this.safeMaxX = this.width - this.zoneWidth;
    this.safeMaxY = this.height - this.zoneWidth;
    this.apples = [];
    this._initApples();
  }

  private _initApples(): void {
    for (let i = 0; i < this.cfg.food_count; i++) {
      const [x, y] = this._randomSafePosition();
      this.apples.push({ x, y, respawn_at_tick: -1 });
    }
  }

  private _randomSafePosition(): [number, number] {
    const margin = 10;
    return [
      this.rng.uniform(this.safeMin + margin, this.safeMaxX - margin),
      this.rng.uniform(this.safeMin + margin, this.safeMaxY - margin),
    ];
  }

  respawnApples(currentTick: number): void {
    for (const apple of this.apples) {
      if (apple.respawn_at_tick > 0 && currentTick >= apple.respawn_at_tick) {
        const [x, y] = this._randomSafePosition();
        apple.x = x;
        apple.y = y;
        apple.respawn_at_tick = -1;
      }
    }
  }

  eatApple(appleIndex: number, currentTick: number): void {
    this.apples[appleIndex].respawn_at_tick = currentTick + this.cfg.food_respawn_delay;
  }

  get foodAvailable(): number {
    return this.apples.filter(a => a.respawn_at_tick < 0).length;
  }

  wallPenaltyDrain(x: number, y: number): number {
    const distToNearestWall = Math.min(x, y, this.width - x, this.height - y);
    if (distToNearestWall >= this.zoneWidth) return 0;
    const ratio = distToNearestWall / this.zoneWidth;
    return this.zoneMaxDrain * (1.0 - ratio);
  }

  clampPosition(x: number, y: number, radius: number): [number, number] {
    return [
      Math.max(radius, Math.min(this.width - radius, x)),
      Math.max(radius, Math.min(this.height - radius, y)),
    ];
  }

  isValidSpawn(x: number, y: number, radius: number): boolean {
    const margin = radius + 5;
    return (
      x > this.zoneWidth + margin &&
      x < this.width - this.zoneWidth - margin &&
      y > this.zoneWidth + margin &&
      y < this.height - this.zoneWidth - margin
    );
  }
}