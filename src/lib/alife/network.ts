// ═══════════════════════════════════════════════════════════════════
//  network.ts — Compiled feedforward neural network from a Genome
//
//  Base: Python network.py (Kahn's algorithm with min-heap)
//  Invariant n°4: topological sort computed ONCE at construction.
//  Hidden → tanh activation, Output → linear.
// ═══════════════════════════════════════════════════════════════════

import { NodeType, type Genome } from './genome';
import type { NetworkConfig } from './config';
import type { SeededRNG } from './genome';

const ACTIVATIONS: Record<string, (x: number) => number> = {
  tanh: Math.tanh,
};

function getActivation(name: string): (x: number) => number {
  const fn = ACTIVATIONS[name];
  if (!fn) throw new Error(`unknown activation '${name}'`);
  return fn;
}

type InEdge = readonly [srcId: number, weight: number];

export class NeuralNetwork {
  private _activation: (x: number) => number;
  private _evalOrder: number[];
  private _nodeTypes: Map<number, string>;
  private _incoming: Map<number, InEdge[]>;
  readonly inputIds: number[];
  readonly outputIds: number[];

  constructor(genome: Genome, _config: NetworkConfig) {
    this._activation = getActivation(_config.activation);

    // Node type lookup
    this._nodeTypes = new Map();
    for (const n of genome.nodes) {
      this._nodeTypes.set(n.id, n.type);
    }

    this.inputIds = genome.inputIds;
    this.outputIds = genome.outputIds;

    // Build incoming adjacency (enabled connections only)
    this._incoming = new Map();
    for (const n of genome.nodes) {
      this._incoming.set(n.id, []);
    }
    for (const conn of genome.connections) {
      if (conn.enabled) {
        this._incoming.get(conn.out_node)!.push([conn.in_node, conn.weight]);
      }
    }

    this._evalOrder = this._topoSort(genome);

    // Safety net: if cycle detected, auto-repair instead of crashing.
    // Should never trigger if mutation guards work, but handles edge cases
    // where multiple toggle mutations in one call interact badly.
    if (this._evalOrder.length !== genome.nodes.length) {
      this._repairCycle(genome);
    }
  }

  /**
   * Kahn's algorithm with min-heap (deterministic ascending node-id order).
   * Returns node IDs in topological order.
   */
  private _topoSort(genome: Genome): number[] {
    const successors = new Map<number, number[]>();
    for (const n of genome.nodes) successors.set(n.id, []);
    for (const conn of genome.connections) {
      if (conn.enabled) {
        successors.get(conn.in_node)!.push(conn.out_node);
      }
    }

    const inDeg = new Map<number, number>();
    for (const n of genome.nodes) inDeg.set(n.id, 0);
    for (const conn of genome.connections) {
      if (conn.enabled) {
        inDeg.set(conn.out_node, (inDeg.get(conn.out_node) || 0) + 1);
      }
    }

    const heap = new MinHeap<number>();
    for (const [nid, deg] of inDeg) {
      if (deg === 0) heap.push(nid);
    }

    const order: number[] = [];
    while (heap.size > 0) {
      const nid = heap.pop()!;
      order.push(nid);
      for (const dst of successors.get(nid) || []) {
        const newDeg = (inDeg.get(dst) || 1) - 1;
        inDeg.set(dst, newDeg);
        if (newDeg === 0) heap.push(dst);
      }
    }
    return order;
  }

  /**
   * Auto-repair a cyclic genome by iteratively disabling edges into
   * unreachable nodes. Falls back to disabling all hidden→hidden edges.
   * Never throws — always produces a valid (possibly degraded) network.
   */
  private _repairCycle(genome: Genome): void {
    // Pass 1: disable edges whose out_node was not in eval order
    const unreachable = new Set<number>();
    for (const n of genome.nodes) {
      if (!this._evalOrder.includes(n.id)) unreachable.add(n.id);
    }
    for (const conn of genome.connections) {
      if (conn.enabled && unreachable.has(conn.out_node)) {
        conn.enabled = false;
      }
    }

    // Rebuild and re-sort
    this._rebuildIncoming(genome);
    this._evalOrder = this._topoSort(genome);

    if (this._evalOrder.length === genome.nodes.length) return; // fixed

    // Pass 2: disable ALL edges involving hidden nodes
    for (const conn of genome.connections) {
      if (conn.enabled) {
        const srcType = this._nodeTypes.get(conn.in_node);
        const dstType = this._nodeTypes.get(conn.out_node);
        if (srcType === NodeType.HIDDEN || dstType === NodeType.HIDDEN) {
          conn.enabled = false;
        }
      }
    }

    this._rebuildIncoming(genome);
    this._evalOrder = this._topoSort(genome);
    // Input→output only graph is always a DAG, so this must succeed
  }

  private _rebuildIncoming(genome: Genome): void {
    this._incoming = new Map();
    for (const n of genome.nodes) {
      this._incoming.set(n.id, []);
    }
    for (const conn of genome.connections) {
      if (conn.enabled) {
        this._incoming.get(conn.out_node)!.push([conn.in_node, conn.weight]);
      }
    }
  }

  /**
   * Forward pass. Returns raw (linear) output values.
   * Caller applies tanh for speed/turn bounding (egocentric invariant n°5).
   *
   * @param rng Optional — used for micro-noise fallback (TS innovation).
   *            If both outputs are exactly 0 (disconnected network), inject noise.
   */
  activate(inputs: number[], rng?: SeededRNG): [number, number] {
    if (inputs.length !== this.inputIds.length) {
      throw new Error(`expected ${this.inputIds.length} inputs, got ${inputs.length}`);
    }

    const values = new Map<number, number>();
    for (let i = 0; i < this.inputIds.length; i++) {
      values.set(this.inputIds[i], inputs[i]);
    }

    for (const nid of this._evalOrder) {
      const ntype = this._nodeTypes.get(nid);
      if (ntype === NodeType.INPUT) continue;

      const edges = this._incoming.get(nid)!;
      let total = 0;
      for (const [src, w] of edges) {
        total += w * (values.get(src) || 0);
      }

      if (ntype === NodeType.OUTPUT) {
        values.set(nid, total); // linear
      } else {
        values.set(nid, this._activation(total)); // tanh for hidden
      }
    }

    let out0 = values.get(this.outputIds[0]) || 0;
    let out1 = values.get(this.outputIds[1]) || 0;

    // Micro-noise fallback (TS innovation): prevent frozen agents
    if (out0 === 0 && out1 === 0 && rng) {
      out0 = rng.gauss(0, 0.1);
      out1 = rng.gauss(0, 0.1);
    }

    return [out0, out1];
  }
}

// ── Min-heap for deterministic Kahn's sort ──────────────────

class MinHeap<T extends number> {
  private _data: T[] = [];

  get size(): number { return this._data.length; }

  push(val: T): void {
    this._data.push(val);
    this._bubbleUp(this._data.length - 1);
  }

  pop(): T | undefined {
    const top = this._data[0];
    const last = this._data.pop();
    if (this._data.length > 0 && last !== undefined) {
      this._data[0] = last;
      this._sinkDown(0);
    }
    return top;
  }

  private _bubbleUp(i: number): void {
    while (i > 0) {
      const parent = (i - 1) >> 1;
      if (this._data[i] < this._data[parent]) {
        [this._data[i], this._data[parent]] = [this._data[parent], this._data[i]];
        i = parent;
      } else break;
    }
  }

  private _sinkDown(i: number): void {
    const n = this._data.length;
    while (true) {
      let smallest = i;
      const left = 2 * i + 1;
      const right = 2 * i + 2;
      if (left < n && this._data[left] < this._data[smallest]) smallest = left;
      if (right < n && this._data[right] < this._data[smallest]) smallest = right;
      if (smallest !== i) {
        [this._data[i], this._data[smallest]] = [this._data[smallest], this._data[i]];
        i = smallest;
      } else break;
    }
  }
}