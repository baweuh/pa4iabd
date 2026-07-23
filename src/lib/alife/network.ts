// ═══════════════════════════════════════════════════════════════════
//  network.ts — Compiled feedforward neural network from a Genome
//
//  Base: Python network.py (Kahn's algorithm with min-heap)
//  Invariant n°4: topological sort computed ONCE at construction.
//  Hidden → tanh activation, Output → linear.
//
//  poc2.6 addition: Reward-modulated Hebbian plasticity.
//    - Optional HebbianConfig at construction (opt-in, zero cost when off)
//    - activate() stores activations for apply_hebbian()
//    - apply_hebbian() does V2 contrastive update every tick
//    - Non-Lamarckian: never writes back to genome
// ═══════════════════════════════════════════════════════════════════

import { NodeType, type Genome } from './genome';
import type { NetworkConfig, HebbianConfig } from './config';
import type { SeededRNG } from './genome';

const ACTIVATIONS: Record<string, (x: number) => number> = {
  tanh: Math.tanh,
};

function getActivation(name: string): (x: number) => number {
  const fn = ACTIVATIONS[name];
  if (!fn) throw new Error(`unknown activation '${name}'`);
  return fn;
}

type InEdge = [srcId: number, weight: number];

export class NeuralNetwork {
  private _activation: (x: number) => number;
  private _evalOrder: number[];
  private _nodeTypes: Map<number, string>;
  private _incoming: Map<number, InEdge[]>;
  private _biasIds: number[];
  readonly inputIds: number[];
  readonly outputIds: number[];

  // poc2.6: Hebbian plasticity state (allocated only when enabled)
  private _hebbian: HebbianConfig | null;
  private _lastValues: Map<number, number> | null = null;
  private _trace: Map<number, number[]> | null = null;
  private _rewardBaseline = 0.0;

  constructor(genome: Genome, _config: NetworkConfig, hebbian?: HebbianConfig) {
    this._activation = getActivation(_config.activation);

    // Plasticity is opt-in and costs the legacy path nothing.
    this._hebbian = (hebbian !== undefined && hebbian.enabled) ? hebbian : null;

    // Node type lookup
    this._nodeTypes = new Map();
    for (const n of genome.nodes) {
      this._nodeTypes.set(n.id, n.type);
    }

    this.inputIds = genome.inputIds;
    this.outputIds = genome.outputIds;
    this._biasIds = genome.biasIds;

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

    // Safety net: auto-repair cycles
    if (this._evalOrder.length !== genome.nodes.length) {
      this._repairCycle(genome);
    }

    // poc2.6: Allocate eligibility traces (parallel to _incoming)
    if (this._hebbian !== null) {
      this._trace = new Map();
      for (const [nid, srcs] of this._incoming) {
        this._trace.set(nid, new Array(srcs.length).fill(0.0));
      }
    }
  }

  /** Kahn's algorithm with min-heap. */
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

  private _repairCycle(genome: Genome): void {
    const unreachable = new Set<number>();
    for (const n of genome.nodes) {
      if (!this._evalOrder.includes(n.id)) unreachable.add(n.id);
    }
    for (const conn of genome.connections) {
      if (conn.enabled && unreachable.has(conn.out_node)) {
        conn.enabled = false;
      }
    }
    this._rebuildIncoming(genome);
    this._evalOrder = this._topoSort(genome);
    if (this._evalOrder.length === genome.nodes.length) return;
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
   * Under Hebbian, stores activations for apply_hebbian().
   */
  activate(inputs: number[], rng?: SeededRNG): [number, number] {
    if (inputs.length !== this.inputIds.length) {
      throw new Error(`expected ${this.inputIds.length} inputs, got ${inputs.length}`);
    }

    const values = new Map<number, number>();
    for (let i = 0; i < this.inputIds.length; i++) {
      values.set(this.inputIds[i], inputs[i]);
    }
    for (const bid of this._biasIds) {
      values.set(bid, 1.0);
    }

    for (const nid of this._evalOrder) {
      const ntype = this._nodeTypes.get(nid);
      if (ntype === NodeType.INPUT || ntype === NodeType.BIAS) continue;

      const edges = this._incoming.get(nid)!;
      let total = 0;
      for (const [src, w] of edges) {
        total += w * (values.get(src) || 0);
      }

      if (ntype === NodeType.OUTPUT) {
        values.set(nid, total);
      } else {
        values.set(nid, this._activation(total));
      }
    }

    // poc2.6: Store activations for Hebbian update
    if (this._hebbian !== null) {
      this._lastValues = values;
    }

    let out0 = values.get(this.outputIds[0]) || 0;
    let out1 = values.get(this.outputIds[1]) || 0;

    if (out0 === 0 && out1 === 0 && rng) {
      out0 = rng.gauss(0, 0.1);
      out1 = rng.gauss(0, 0.1);
    }

    return [out0, out1];
  }

  /**
   * Advance eligibility traces and apply one contrastive Hebbian update.
   *
   * Called once per tick per agent (V2 — every tick, not just capture ticks):
   *   e  <- eligibility_decay * e + x * y
   *   dw = learning_rate * (reward - baseline) * e
   *
   * The baseline is read BEFORE folding in this tick's reward (genuine surprise signal).
   * Clamped to ±hebbian.weight_max. No-op when plasticity is off.
   *
   * CRITICAL: NOT called from activate(). Several callers activate a network
   * purely to measure it (steer_score, novelty descriptor, HyperNEAT CPPN queries)
   * and observing an agent must never modify its brain.
   */
  applyHebbian(reward: number): void {
    if (this._hebbian === null || this._lastValues === null) return;

    const values = this._lastValues;
    const cfg = this._hebbian;
    const decay = cfg.eligibility_decay;
    const limit = cfg.weight_max;

    // Contrast against expected BEFORE this tick's outcome
    const step = cfg.learning_rate * (reward - this._rewardBaseline);
    this._rewardBaseline += cfg.baseline_rate * (reward - this._rewardBaseline);

    for (const [nid, srcs] of this._incoming) {
      if (srcs.length === 0) continue;
      let post = values.get(nid) ?? 0;
      // Output nodes are linear, but Agent applies tanh to use them.
      // Learning on the emitted value keeps x and y in (-1, 1).
      if (this._nodeTypes.get(nid) === NodeType.OUTPUT) {
        post = Math.tanh(post);
      }
      const trace = this._trace!.get(nid)!;
      for (let pos = 0; pos < srcs.length; pos++) {
        const pre = values.get(srcs[pos][0]) ?? 0;
        const e = decay * trace[pos] + pre * post;
        trace[pos] = e;
        srcs[pos][1] = Math.max(-limit, Math.min(limit, srcs[pos][1] + step * e));
      }
    }
  }
}

// ── Min-heap for deterministic Kahn's sort ──────────────────

class MinHeap<T extends number> {
  private _data: T[] = [];
  get size(): number { return this._data.length; }
  push(val: T): void { this._data.push(val); this._bubbleUp(this._data.length - 1); }
  pop(): T | undefined {
    const top = this._data[0];
    const last = this._data.pop();
    if (this._data.length > 0 && last !== undefined) {
      this._data[0] = last; this._sinkDown(0);
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
