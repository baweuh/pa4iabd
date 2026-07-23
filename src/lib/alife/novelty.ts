// ═══════════════════════════════════════════════════════════════════
//  novelty.ts — Behavioural novelty for additive reproduction bonuses
//
//  Ported from Python src/novelty.py (Lehman & Stanley 2011).
//
//  A network's behaviour is characterised by its *steering response profile*:
//  the turn output it produces to a lone apple placed on each ray.
//  This depends only on the network (frozen weights, topology sorted once),
//  so the descriptor is deterministic and computed once per agent (cached).
//
//  Novelty is the mean distance to the `neighbors` nearest behaviours.
//  In simulation.ts it is ADDED to raw fitness — never replacing it.
//  Additive is the only pattern that held up on this project.
// ═══════════════════════════════════════════════════════════════════

import type { SensorConfig } from './config';
import type { NeuralNetwork } from './network';

/**
 * Build a sensor vector with a single apple on ray `k` (layout-aware).
 * Mirrors Python _probe_input().
 */
function probeInput(k: number, sensors: SensorConfig, numInputs: number): number[] {
  const numRays = sensors.num_rays;
  const appleDist = new Array(numRays).fill(1.0);
  appleDist[k] = 0.2; // a close apple on ray k
  const wallDist = new Array(numRays).fill(1.0);
  const appleFlag = new Array(numRays).fill(0.0);
  appleFlag[k] = 1.0;
  const wallFlag = new Array(numRays).fill(0.0);

  let vec: number[];
  if (sensors.split_distance) {
    vec = [...appleDist, ...wallDist, ...appleFlag, ...wallFlag];
  } else {
    const combined = appleDist.map((a, i) => Math.min(a, wallDist[i]));
    vec = [...combined, ...appleFlag, ...wallFlag];
  }

  vec.push(0.5); // energy at mid-range
  if (sensors.proprioception) vec.push(0.0); // actual_speed: still
  if (sensors.apples_in_view) vec.push(1.0 / numRays); // exactly one ray sees apple

  // Pad or truncate to match numInputs (safety for layout mismatches)
  while (vec.length < numInputs) vec.push(0.0);
  return vec.slice(0, numInputs);
}

/**
 * Turn-response profile: tanh(turn output) to an apple on each ray.
 * Length = num_rays. Cached on the Agent for life (like the network topo-sort).
 */
export function behaviorDescriptor(
  net: NeuralNetwork,
  sensors: SensorConfig,
  numInputs: number,
): number[] {
  return Array.from({ length: sensors.num_rays }, (_, k) => {
    const probe = probeInput(k, sensors, numInputs);
    const [, turnRaw] = net.activate(probe);
    return Math.tanh(turnRaw);
  });
}

/**
 * Mean distance to the `neighbors` nearest behaviours, per agent.
 *
 * `descriptors` is (P, D) as a flat array (P * D floats), returns (P,).
 * Self is excluded. With fewer than `neighbors` others, averages over all.
 * 0/1-agent populations have novelty 0 everywhere (unless archive).
 *
 * `archive` is an optional (A, D) flat array — a pool of past behaviours
 * that widens the neighbourhood without being scored itself.
 */
export function populationNovelty(
  descriptors: number[][],   // P descriptors, each of length D
  neighbors: number,
  archive: number[][] | null = null,
): number[] {
  const count = descriptors.length;
  const hasArchive = archive !== null && archive.length > 0;
  if (count <= 1 && !hasArchive) {
    return new Array(count).fill(0);
  }

  const pool = hasArchive ? [...descriptors, ...archive!] : descriptors;
  const D = descriptors[0]?.length ?? 0;
  const result: number[] = [];

  for (let i = 0; i < count; i++) {
    const di = descriptors[i];
    // Compute distances to all pool members
    const dists: number[] = [];
    for (let j = 0; j < pool.length; j++) {
      if (j < count && j === i) continue; // skip self
      const dj = pool[j];
      let sumSq = 0;
      for (let d = 0; d < D; d++) {
        const diff = di[d] - dj[d];
        sumSq += diff * diff;
      }
      dists.push(Math.sqrt(sumSq));
    }

    if (dists.length === 0) {
      result.push(0);
      continue;
    }

    // k smallest (partial sort via selection for small k)
    const k = Math.min(neighbors, dists.length);
    // Simple selection of k smallest
    const indices = dists.map((_, idx) => idx);
    for (let s = 0; s < k; s++) {
      let minIdx = s;
      for (let t = s + 1; t < indices.length; t++) {
        if (dists[indices[t]] < dists[indices[minIdx]]) minIdx = t;
      }
      [indices[s], indices[minIdx]] = [indices[minIdx], indices[s]];
    }

    let sum = 0;
    for (let s = 0; s < k; s++) {
      sum += dists[indices[s]];
    }
    result.push(sum / k);
  }

  return result;
}