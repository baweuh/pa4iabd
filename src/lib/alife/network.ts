// ═══════════════════════════════════════════════════════════════════
//  network.ts — Compiled feedforward neural network from a Genome
//
//  Base: Python network.py (Kahn's algorithm with min-heap)
//  Invariant n°4: topological sort computed ONCE at construction.
//  Hidden → tanh activation, Output → linear.
// ═══════════════════════════════════════════════════════════════════

import { NodeType, type Genome } from './genome';
import type { NetworkConfig, SeededRNG } from './config';

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

    // Kahn's algorithm with min-heap (deterministic ascending node-id order)
    const inDeg = new Map<number, number>();
    for (const [nid, edges] of this._incoming) {
      inDeg.set(nid, edges.length);
    }
    const heap = new MinHeap<number>();
    for (const [nid, deg] of inDeg) {
      if (deg === 0) heap.push(nid);
    }

    // Successors for decrementing in-degrees
    const successors = new Map<number, number[]>();
    for (const n of genome.nodes) successors.set(n.id, []);
    for (const conn of genome.connections) {
      if (conn.enabled) {
        successors.get(conn.in_node)!.push(conn.out_node);
      }
    }

    const evalOrder: number[] = [];
    while (heap.size > 0) {
      const nid = heap.pop()!;
      evalOrder.push(nid);
      for (const dst of successors.get(nid) || []) {
        const newDeg = (inDeg.get(dst) || 1) - 1;
        inDeg.set(dst, newDeg);
        if (newDeg === 0) heap.push(dst);
      }
    }

    if (evalOrder.length !== genome.nodes.length) {
      throw new Error(
        `genome contains a cycle — processed ${evalOrder.length}/${genome.nodes.length} nodes`
      );
    }

    this._evalOrder = evalOrder;
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