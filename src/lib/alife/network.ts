// ═══════════════════════════════════════════════════════════
//  network.ts — Forward pass from Genome, topological sort
//  Porté de src/network.py
// ═══════════════════════════════════════════════════════════

import { Genome, NodeType } from './genome';

function activationFn(name: string): (x: number) => number {
  if (name === 'sigmoid') return (x: number) => 1.0 / (1.0 + Math.exp(-Math.max(-500, Math.min(500, x))));
  return Math.tanh; // default
}

export class NeuralNetwork {
  genome: Genome;
  networkSize: number;

  private order: number[];
  private connList: { inIdx: number; outIdx: number; weight: number }[];
  private activations: Map<number, (x: number) => number>;
  private inputPositions: number[];
  private outputPositions: number[];

  constructor(genome: Genome) {
    this.genome = genome;
    const result = this._build();
    this.order = result.order;
    this.connList = result.connList;
    this.activations = result.activations;
    this.inputPositions = result.inputPositions;
    this.outputPositions = result.outputPositions;
    this.networkSize = this.connList.length;
  }

  private _build() {
    const g = this.genome;
    const order = this._topologicalSort();
    const idxMap = new Map<number, number>();
    for (let i = 0; i < order.length; i++) idxMap.set(order[i], i);

    const connList: { inIdx: number; outIdx: number; weight: number }[] = [];
    for (const conn of g.enabledConnections) {
      const inIdx = idxMap.get(conn.in_node_id);
      const outIdx = idxMap.get(conn.out_node_id);
      if (inIdx !== undefined && outIdx !== undefined) {
        connList.push({ inIdx, outIdx, weight: conn.weight });
      }
    }

    const activations = new Map<number, (x: number) => number>();
    for (const [nid, node] of g.nodes) {
      activations.set(nid, node.type === NodeType.INPUT ? (x: number) => x : activationFn(node.activation));
    }

    const inputIds = [...g.nodes.values()].filter(n => n.type === NodeType.INPUT).map(n => n.id).sort((a, b) => a - b);
    const outputIds = [...g.nodes.values()].filter(n => n.type === NodeType.OUTPUT).map(n => n.id).sort((a, b) => a - b);

    const inputPositions = inputIds.map(id => idxMap.get(id)!).filter(x => x !== undefined);
    const outputPositions = outputIds.map(id => idxMap.get(id)!).filter(x => x !== undefined);

    return { order, connList, activations, inputPositions, outputPositions };
  }

  private _topologicalSort(): number[] {
    const g = this.genome;
    const inDegree = new Map<number, number>();
    const adj = new Map<number, number[]>();

    for (const nid of g.nodes.keys()) {
      inDegree.set(nid, 0);
      adj.set(nid, []);
    }

    for (const conn of g.enabledConnections) {
      if (g.nodes.has(conn.in_node_id) && g.nodes.has(conn.out_node_id)) {
        adj.get(conn.in_node_id)!.push(conn.out_node_id);
        inDegree.set(conn.out_node_id, (inDegree.get(conn.out_node_id) || 0) + 1);
      }
    }

    const queue: number[] = [...inDegree.entries()].filter(([, deg]) => deg === 0).map(([id]) => id).sort((a, b) => a - b);
    const order: number[] = [];

    while (queue.length > 0) {
      const node = queue.shift()!;
      order.push(node);
      const neighbors = (adj.get(node) || []).sort((a, b) => a - b);
      for (const neighbor of neighbors) {
        const deg = (inDegree.get(neighbor) || 1) - 1;
        inDegree.set(neighbor, deg);
        if (deg === 0) {
          queue.push(neighbor);
          queue.sort((a, b) => a - b);
        }
      }
    }

    // If cycle detected, just return all nodes (degraded mode)
    if (order.length !== g.nodes.size) {
      return [...g.nodes.keys()].sort((a, b) => a - b);
    }

    return order;
  }

  activate(inputs: number[]): number[] {
    const n = this.order.length;
    const acts = new Float64Array(n);

    // Inject inputs
    for (let i = 0; i < this.inputPositions.length && i < inputs.length; i++) {
      acts[this.inputPositions[i]] = inputs[i];
    }

    // Propagate
    for (const { inIdx, outIdx, weight } of this.connList) {
      acts[outIdx] += weight * acts[inIdx];
    }

    // Apply activations
    for (let i = 0; i < this.order.length; i++) {
      const nid = this.order[i];
      const node = this.genome.nodes.get(nid);
      if (node && node.type !== NodeType.INPUT) {
        const fn = this.activations.get(nid) || Math.tanh;
        acts[i] = fn(acts[i]);
      }
    }

    return [...this.outputPositions.map(pos => acts[pos])];
  }
}