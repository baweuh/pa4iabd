// ══════════════════════════════════════════════════════════════════════════════
//  geometry.ts — Pure geometry helpers shared across perception, HyperNEAT.
//
//  Ported from Python src/geometry.py (poc2.5).
//  Shared by perception (agent.ts) and HyperNEAT substrate coordinates
//  so they always agree on ray geometry. No import cycle.
// ══════════════════════════════════════════════════════════════════════════════

/**
 * Egocentric ray angles (radians) centred on `heading`.
 *
 * Ray 0 is the forward direction (`heading`); subsequent rays are spaced
 * evenly across the full `fovDegrees`. With fov == 360 the rays cover
 * the full circle. Shared by perception, the renderer, and HyperNEAT
 * substrate coordinates so they always agree on ray geometry.
 */
export function rayAngles(numRays: number, fovDegrees: number, heading = 0.0): number[] {
  const step = (Math.PI * fovDegrees / 180) / numRays;
  const angles: number[] = [];
  for (let i = 0; i < numRays; i++) {
    angles.push(heading + i * step);
  }
  return angles;
}

/** Clamp `value` to [low, high]. */
export function clamp(value: number, low: number, high: number): number {
  return Math.max(low, Math.min(high, value));
}
