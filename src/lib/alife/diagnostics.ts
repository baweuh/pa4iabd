// ══════════════════════════════════════════════════════════════════════════════
//  diagnostics.ts — Observational instrumentation: capture classification,
//                      density, N_e
//
//  Ported from Python src/diagnostics.py (poc2.4/poc2.6).
//  Every function here is read-only with respect to the simulation:
//  pure functions over positions/counts, never feeds back into agent
//  decisions, reproduction or mutation (CSV-only diagnostics).
// ══════════════════════════════════════════════════════════════════════════════

import type { AgentConfig, DiagnosticsConfig, SensorConfig } from './config';
import type { NeuralNetwork } from './network';
import { probeInput } from './novelty';

export const ADJACENT = 'adjacent';
export const DIRECTED = 'directed';
export const UNDIRECTED = 'undirected';

/**
 * Pearson r between 'apple on the left' and 'turns left'.
 * 1.0 = perfect forager, 0.0 = ignores apples, negative = anti-forager.
 * Deterministic from the (frozen) network.
 */
export function steerScore(net: NeuralNetwork, sensors: SensorConfig, numInputs: number): number {
  const numRays = sensors.num_rays;
  const xs: number[] = [];
  const ys: number[] = [];
  for (let k = 1; k < numRays; k++) {
    if (k === Math.floor(numRays / 2)) continue; // directly behind: ambiguous
    const ang = k * (2 * Math.PI / numRays);
    const probe = probeInput(k, sensors, numInputs);
    const raw = net.activate(probe);
    xs.push(Math.sin(ang));
    ys.push(Math.tanh(raw[1]));
  }
  const n = xs.length;
  if (n === 0) return 0.0;
  const mx = xs.reduce((a, b) => a + b, 0) / n;
  const my = ys.reduce((a, b) => a + b, 0) / n;
  let num = 0;
  let dx = 0;
  let dy = 0;
  for (let i = 0; i < n; i++) {
    const a = xs[i] - mx;
    const b = ys[i] - my;
    num += a * b;
    dx += a * a;
    dy += b * b;
  }
  const denom = Math.sqrt(dx) * Math.sqrt(dy);
  return denom > 1e-12 ? num / denom : 0.0;
}

/** Ticks needed to cross the whole sensing range at max speed (>= 1). */
export function captureLookbackTicks(sensors: SensorConfig, agent: AgentConfig): number {
  return Math.max(1, Math.ceil(sensors.max_distance / agent.max_speed));
}

/**
 * Classify one capture as ADJACENT / DIRECTED / UNDIRECTED.
 * ref_* is the agent's position/heading at (or just after) the apple's spawn_tick.
 */
export function classifyCapture(
  appleX: number, appleY: number,
  refX: number, refY: number, refHeading: number,
  reach: number, cfg: DiagnosticsConfig,
): string {
  const dist0 = Math.hypot(appleX - refX, appleY - refY);
  if (dist0 <= reach * cfg.capture_close_mult) return ADJACENT;
  let bearing = Math.atan2(appleY - refY, appleX - refX) - refHeading;
  bearing = ((bearing + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI;
  const ahead = Math.abs((bearing * 180) / Math.PI) <= cfg.capture_ahead_degrees;
  const ratio = Math.max(0, (dist0 - reach) / dist0);
  return ahead && ratio >= cfg.capture_directed_ratio ? DIRECTED : UNDIRECTED;
}

/** Count of OTHER agents within `radius` (excludes itself). */
export function localAgentDensity(
  agent: { x: number; y: number },
  population: { x: number; y: number }[],
  radius: number,
): number {
  const r2 = radius * radius;
  let count = 0;
  for (const other of population) {
    if (other !== agent) {
      const dx = other.x - agent.x;
      const dy = other.y - agent.y;
      if (dx * dx + dy * dy <= r2) count++;
    }
  }
  return count;
}

/** Count of OTHER apples within `radius` (excludes itself). */
export function localAppleDensity(
  apple: { x: number; y: number },
  apples: { x: number; y: number }[],
  radius: number,
): number {
  const r2 = radius * radius;
  let count = 0;
  for (const other of apples) {
    if (other !== apple) {
      const dx = other.x - apple.x;
      const dy = other.y - apple.y;
      if (dx * dx + dy * dy <= r2) count++;
    }
  }
  return count;
}

/** Count per unit area — a single map-wide number. */
export function globalDensity(count: number, worldWidth: number, worldHeight: number): number {
  return count / (worldWidth * worldHeight);
}

/**
 * Crow & Kimura N_e ≈ N / (1 + Var(k) / mean(k)).
 * `offspringCounts`: one entry per individual (0 for non-reproducers).
 */
export function effectivePopulationSize(offspringCounts: number[]): number {
  const n = offspringCounts.length;
  if (n === 0) return 0.0;
  const sum = offspringCounts.reduce((a, b) => a + b, 0);
  const meanK = sum / n;
  if (meanK <= 0) return n;
  let varK = 0;
  for (const k of offspringCounts) {
    const d = k - meanK;
    varK += d * d;
  }
  varK /= n;
  return n / (1 + varK / meanK);
}
