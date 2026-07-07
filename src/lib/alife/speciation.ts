// ═══════════════════════════════════════════════════════════════════
//  speciation.ts — NEAT compatibility distance (read-only observer)
//
//  Base: Python speciation.py
//  Never influences selection or reproduction — pure observability.
//  delta = c_excess * E + c_disjoint * D + c_weight * W
// ═══════════════════════════════════════════════════════════════════

import type { SpeciationConfig } from './config';
import type { Genome } from './genome';

export function compatibilityDistance(
  first: Genome, second: Genome, config: SpeciationConfig,
): number {
  const weightsA = new Map<number, number>();
  for (const c of first.connections) weightsA.set(c.innovation, c.weight);

  const weightsB = new Map<number, number>();
  for (const c of second.connections) weightsB.set(c.innovation, c.weight);

  if (weightsA.size === 0 && weightsB.size === 0) return 0.0;

  const innovA = new Set(weightsA.keys());
  const innovB = new Set(weightsB.keys());
  const matching = new Set([...innovA].filter(x => innovB.has(x)));

  // Boundary = min of max innovations
  const maxA = Math.max(0, ...innovA);
  const maxB = Math.max(0, ...innovB);
  const boundary = Math.min(maxA, maxB);

  let excess = 0;
  let disjoint = 0;
  for (const innov of innovA) {
    if (!innovB.has(innov)) {
      if (innov > boundary) excess++;
      else disjoint++;
    }
  }
  for (const innov of innovB) {
    if (!innovA.has(innov)) {
      if (innov > boundary) excess++;
      else disjoint++;
    }
  }

  let weightDiff = 0.0;
  if (matching.size > 0) {
    let total = 0;
    for (const innov of matching) {
      total += Math.abs((weightsA.get(innov) || 0) - (weightsB.get(innov) || 0));
    }
    weightDiff = total / matching.size;
  }

  return config.c_excess * excess + config.c_disjoint * disjoint + config.c_weight * weightDiff;
}

export function countSpecies(genomes: Genome[], config: SpeciationConfig): number {
  const representatives: Genome[] = [];
  for (const genome of genomes) {
    if (!representatives.some(rep => compatibilityDistance(genome, rep, config) < config.compatibility_threshold)) {
      representatives.push(genome);
    }
  }
  return representatives.length;
}

export function meanPairwiseDistance(genomes: Genome[], config: SpeciationConfig): number {
  const n = genomes.length;
  if (n < 2) return 0.0;
  let total = 0;
  let pairs = 0;
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      total += compatibilityDistance(genomes[i], genomes[j], config);
      pairs++;
    }
  }
  return pairs > 0 ? total / pairs : 0.0;
}