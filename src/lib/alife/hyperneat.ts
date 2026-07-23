// ══════════════════════════════════════════════════════════════════════════════
//  hyperneat.ts — Indirect encoding: derive a substrate network from a CPPN.
//
//  Ported from Python src/hyperneat.py (poc2.5).
//  The genome evolves a small CPPN (Compositional Pattern-Producing Network) that
//  maps substrate-node coordinate pairs to connection weights.
//  The substrate itself is FIXED (no hidden layer for this MVP).
// ══════════════════════════════════════════════════════════════════════════════

import type { HyperNEATConfig, NetworkConfig, SensorConfig } from './config';
import { NodeType, Genome, InnovationTracker, type ConnectionGene } from './genome';
import { rayAngles } from './geometry';
import { NeuralNetwork } from './network';

// CPPN query: (x, y, z) for each of the two queried substrate nodes.
export const CPPN_NUM_INPUTS = 6;
// CPPN answer: one raw connection weight.
export const CPPN_NUM_OUTPUTS = 1;

// Fixed, off-ring coordinates for the 2 substrate outputs (speed, turn).
const _OUTPUT_COORDS: readonly (readonly [number, number, number])[] = [
  [-0.5, -1.5, 0.0],
  [0.5, -1.5, 0.0],
];

/**
 * Return one (x, y, z) per substrate input, in Agent.sense() order.
 *
 * Length always equals sensors.num_inputs — every sensor toggle combination
 * is supported (invariant n°1: layout is derived from config, never hardcoded).
 */
export function substrateInputCoords(sensors: SensorConfig): [number, number, number][] {
  const ringKinds: string[] = sensors.split_distance
    ? ['apple_dist', 'wall_dist', 'apple_flag', 'wall_flag']
    : ['dist', 'apple_flag', 'wall_flag'];

  const scalarKinds: string[] = ['energy'];
  if (sensors.proprioception) scalarKinds.push('actual_speed');
  if (sensors.apples_in_view) scalarKinds.push('apples_in_view');

  const kinds = [...ringKinds, ...scalarKinds];
  const nKinds = kinds.length;
  const zOf = new Map<string, number>();
  for (let i = 0; i < nKinds; i++) {
    zOf.set(kinds[i], nKinds > 1 ? (2 * i) / (nKinds - 1) - 1 : 0);
  }

  const angles = rayAngles(sensors.num_rays, sensors.fov, 0.0);
  const coords: [number, number, number][] = [];

  for (const kind of ringKinds) {
    const z = zOf.get(kind)!;
    for (const a of angles) {
      coords.push([Math.cos(a), Math.sin(a), z]);
    }
  }
  for (const kind of scalarKinds) {
    coords.push([0.0, 0.0, zOf.get(kind)!]);
  }
  return coords;
}

/**
 * Query cppnNet for every (input, output) pair to build the substrate genome.
 * Returns a fresh, throwaway Genome (never mutated or evolved itself).
 */
function buildSubstrateGenome(
  cppnNet: NeuralNetwork,
  sensors: SensorConfig,
  hyperneatConfig: HyperNEATConfig,
): Genome {
  const inputCoords = substrateInputCoords(sensors);
  const numInputs = inputCoords.length;
  const numOutputs = _OUTPUT_COORDS.length;

  const nodes = [];
  for (let i = 0; i < numInputs; i++) {
    nodes.push({ id: i, type: NodeType.INPUT });
  }
  for (let j = 0; j < numOutputs; j++) {
    nodes.push({ id: numInputs + j, type: NodeType.OUTPUT });
  }

  // Query every (input, output) pair
  const edges: [number, number, number][] = [];
  for (let i = 0; i < numInputs; i++) {
    const [x1, y1, z1] = inputCoords[i];
    for (let j = 0; j < numOutputs; j++) {
      const [x2, y2, z2] = _OUTPUT_COORDS[j];
      const rawWeight = cppnNet.activate([x1, y1, z1, x2, y2, z2])[0];
      const weight = Math.tanh(rawWeight) * hyperneatConfig.weight_scale;
      edges.push([i, numInputs + j, weight]);
    }
  }

  // Apply connectivity sparsification
  const selected = selectEdges(edges, hyperneatConfig.connectivity);

  const tracker = new InnovationTracker();
  const connections: ConnectionGene[] = selected.map(([inNode, outNode, weight]) => ({
    in_node: inNode,
    out_node: outNode,
    weight,
    enabled: true,
    innovation: tracker.innovationFor(inNode, outNode),
  }));

  // Build genome via reflection-free constructor
  const genome = new Genome(numInputs, numOutputs);
  genome.nodes = nodes;
  genome.connections = connections;
  genome.ray_range = 0;
  return genome;
}

/**
 * Keep the top-`connectivity` fraction of edges per output, by |weight|.
 * connectivity >= 1.0 returns edges unchanged.
 */
function selectEdges(
  edges: [number, number, number][],
  connectivity: number,
): [number, number, number][] {
  if (connectivity >= 1.0) return edges;

  const byOutput = new Map<number, [number, number, number][]>();
  for (const edge of edges) {
    const group = byOutput.get(edge[1]);
    if (group) { group.push(edge); } else { byOutput.set(edge[1], [edge]); }
  }

  const kept = new Set<string>();
  for (const group of byOutput.values()) {
    const k = Math.max(1, Math.round(connectivity * group.length));
    const ranked = [...group].sort((a, b) => Math.abs(b[2]) - Math.abs(a[2]));
    for (let i = 0; i < k; i++) {
      kept.add(`${ranked[i][0]},${ranked[i][1]}`);
    }
  }

  return edges.filter(e => kept.has(`${e[0]},${e[1]}`));
}

/**
 * Build the executable substrate network an agent actually runs.
 * `cppnGenome` is evolved normally; `networkConfig` is reused as-is.
 */
export function buildSubstrateNetwork(
  cppnGenome: Genome,
  sensors: SensorConfig,
  networkConfig: NetworkConfig,
  hyperneatConfig: HyperNEATConfig,
  hebbianConfig?: import('./config').HebbianConfig,
): NeuralNetwork {
  const cppnNet = new NeuralNetwork(cppnGenome, networkConfig);
  const substrateGenome = buildSubstrateGenome(cppnNet, sensors, hyperneatConfig);
  return new NeuralNetwork(substrateGenome, networkConfig, hebbianConfig);
}
