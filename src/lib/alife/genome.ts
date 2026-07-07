// ═══════════════════════════════════════════════════════════════════
//  genome.ts — NEAT genome, innovation tracker, mutation operators
//
//  Base: Python genome.py (InnovationTracker, canonical NEAT mutations)
//  + TS innovations: connection toggle, evolvable ray_range,
//    output-protection on remove, weight perturb+reset split
// ═══════════════════════════════════════════════════════════════════

import type { GenomeConfig, SensorConfig } from './config';

// ── Enums ────────────────────────────────────────────────────

export const NodeType = {
  INPUT: 'INPUT',
  HIDDEN: 'HIDDEN',
  OUTPUT: 'OUTPUT',
} as const;
export type NodeType = (typeof NodeType)[keyof typeof NodeType];

// ── Gene types ───────────────────────────────────────────────

export interface NodeGene {
  readonly id: number;
  readonly type: NodeType;
}

export interface ConnectionGene {
  in_node: number;
  out_node: number;
  weight: number;
  enabled: boolean;
  innovation: number;
}

// ── Innovation Tracker (module-level, reset per simulation) ──

export class InnovationTracker {
  private _nodeCounter = 0;
  private _innovationCounter = 0;
  private _edgeInnovations = new Map<string, number>();

  reset(): void {
    this._nodeCounter = 0;
    this._innovationCounter = 0;
    this._edgeInnovations.clear();
  }

  bumpNodeFloor(floor: number): void {
    this._nodeCounter = Math.max(this._nodeCounter, floor);
  }

  nextNodeId(): number {
    const id = this._nodeCounter;
    this._nodeCounter++;
    return id;
  }

  innovationFor(inNode: number, outNode: number): number {
    const key = `${inNode},${outNode}`;
    let val = this._edgeInnovations.get(key);
    if (val === undefined) {
      val = this._innovationCounter++;
      this._edgeInnovations.set(key, val);
    }
    return val;
  }
}

export const TRACKER = new InnovationTracker();

// ── Seeded PRNG (Mulberry32) — deterministic, no Math.random ──

export class SeededRNG {
  private state: number;

  constructor(seed: number) {
    this.state = seed | 0;
  }

  /** Float in [0, 1) */
  next(): number {
    let t = (this.state += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }

  /** Float in [min, max) */
  uniform(min: number, max: number): number {
    return min + this.next() * (max - min);
  }

  /** Gaussian via Box-Muller */
  gauss(mean: number, std: number): number {
    const u1 = this.next() || 1e-10;
    const u2 = this.next();
    return mean + std * Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
  }

  /** Random int in [0, max) */
  int(max: number): number {
    return Math.floor(this.next() * max);
  }

  /** Pick random element */
  pick<T>(arr: readonly T[]): T {
    return arr[this.int(arr.length)];
  }

  /** Pick N without replacement */
  sample<T>(arr: readonly T[], n: number): T[] {
    const copy = [...arr];
    const result: T[] = [];
    const count = Math.min(n, copy.length);
    for (let i = 0; i < count; i++) {
      const idx = this.int(copy.length - i);
      result.push(copy.splice(idx, 1)[0]);
    }
    return result;
  }
}

// ── Genome ────────────────────────────────────────────────────

export class Genome {
  nodes: NodeGene[] = [];
  connections: ConnectionGene[] = [];
  ray_range: number;

  private _numInputs: number;
  private _numOutputs: number;

  get numInputs(): number { return this._numInputs; }
  get numOutputs(): number { return this._numOutputs; }

  get inputIds(): number[] {
    return this.nodes.filter(n => n.type === NodeType.INPUT).map(n => n.id).sort((a, b) => a - b);
  }

  get outputIds(): number[] {
    return this.nodes.filter(n => n.type === NodeType.OUTPUT).map(n => n.id).sort((a, b) => a - b);
  }

  get hiddenIds(): number[] {
    return this.nodes.filter(n => n.type === NodeType.HIDDEN).map(n => n.id);
  }

  get enabledConnections(): ConnectionGene[] {
    return this.connections.filter(c => c.enabled);
  }

  get maxInnovation(): number {
    if (this.connections.length === 0) return 0;
    return Math.max(...this.connections.map(c => c.innovation));
  }

  private constructor(numInputs: number, numOutputs: number) {
    this._numInputs = numInputs;
    this._numOutputs = numOutputs;
    this.ray_range = 0; // set by factory methods
  }

  // ── Factory ──────────────────────────────────────────────

  static newFullyConnected(
    numInputs: number,
    numOutputs: number,
    cfg: GenomeConfig,
    sensorCfg: SensorConfig,
    rng: SeededRNG,
    tracker: InnovationTracker = TRACKER,
  ): Genome {
    const g = new Genome(numInputs, numOutputs);
    tracker.bumpNodeFloor(numInputs + numOutputs);

    // Input nodes 0..numInputs-1
    for (let i = 0; i < numInputs; i++) {
      g.nodes.push({ id: i, type: NodeType.INPUT });
    }
    // Output nodes numInputs..numInputs+numOutputs-1
    for (let j = 0; j < numOutputs; j++) {
      g.nodes.push({ id: numInputs + j, type: NodeType.OUTPUT });
    }

    // Fully connected input → output
    for (let i = 0; i < numInputs; i++) {
      for (let j = 0; j < numOutputs; j++) {
        const oid = numInputs + j;
        g.connections.push({
          in_node: i,
          out_node: oid,
          weight: rng.uniform(-cfg.weight_init_range, cfg.weight_init_range),
          enabled: true,
          innovation: tracker.innovationFor(i, oid),
        });
      }
    }

    // Evolvable ray range (TS innovation)
    g.ray_range = rng.uniform(sensorCfg.ray_range_init_min, sensorCfg.ray_range_init_max);

    return g;
  }

  // ── Clone ────────────────────────────────────────────────

  clone(): Genome {
    const g = new Genome(this._numInputs, this._numOutputs);
    g.ray_range = this.ray_range;
    g.nodes = this.nodes.map(n => ({ ...n }));
    g.connections = this.connections.map(c => ({ ...c }));
    return g;
  }

  // ── Serialisation ────────────────────────────────────────

  toDict(): object {
    return {
      ray_range: this.ray_range,
      nodes: this.nodes.map(n => ({ id: n.id, type: n.type })),
      connections: this.connections.map(c => ({
        in: c.in_node, out: c.out_node,
        weight: c.weight, enabled: c.enabled, innovation: c.innovation,
      })),
    };
  }

  static fromDict(data: Record<string, unknown>, numInputs: number, numOutputs: number): Genome {
    const d = data as {
      ray_range: number;
      nodes: { id: number; type: string }[];
      connections: { in: number; out: number; weight: number; enabled: boolean; innovation: number }[];
    };
    const g = new Genome(numInputs, numOutputs);
    g.ray_range = d.ray_range;
    g.nodes = d.nodes.map(n => ({ id: n.id, type: n.type as NodeType }));
    g.connections = d.connections.map(c => ({
      in_node: c.in, out_node: c.out,
      weight: c.weight, enabled: c.enabled, innovation: c.innovation,
    }));
    return g;
  }

  toJSON(): string {
    return JSON.stringify(this.toDict());
  }

  static fromJSON(text: string, numInputs: number, numOutputs: number): Genome {
    return Genome.fromDict(JSON.parse(text), numInputs, numOutputs);
  }

  // ── Mutations ────────────────────────────────────────────

  mutate(cfg: GenomeConfig, rng: SeededRNG, tracker: InnovationTracker = TRACKER): void {
    this._mutateWeights(cfg, rng);
    if (rng.next() < cfg.add_connection_rate) this._addConnection(cfg, rng, tracker);
    if (rng.next() < cfg.add_node_rate) this._addNode(rng, tracker);
    if (rng.next() < cfg.remove_connection_rate) this._removeConnection(rng);
    if (rng.next() < cfg.remove_node_rate) this._removeNode(rng);
    this._toggleConnections(cfg, rng);
  }

  private _mutateWeights(cfg: GenomeConfig, rng: SeededRNG): void {
    for (const conn of this.connections) {
      if (rng.next() < cfg.weight_mutation_rate) {
        const r = rng.next();
        if (r < (1 - cfg.weight_reset_rate)) {
          // Perturb
          conn.weight += rng.gauss(0, cfg.weight_perturbation);
        } else {
          // Reset
          conn.weight = rng.uniform(-cfg.weight_init_range, cfg.weight_init_range);
        }
        // Clamp (anti-saturation)
        conn.weight = Math.max(-cfg.weight_max, Math.min(cfg.weight_max, conn.weight));
      }
    }
  }

  private _addConnection(cfg: GenomeConfig, rng: SeededRNG, tracker: InnovationTracker): void {
    const sources = this.nodes.filter(n => n.type !== NodeType.OUTPUT);
    const targets = this.nodes.filter(n => n.type !== NodeType.INPUT);
    if (sources.length === 0 || targets.length === 0) return;

    for (let attempt = 0; attempt < 10; attempt++) {
      const src = rng.pick(sources);
      const dst = rng.pick(targets);
      if (src.id === dst.id) continue;

      // Try src→dst then dst→src (Python pattern)
      for (const [a, b] of [[src.id, dst.id], [dst.id, src.id]]) {
        if (this._edgeExists(a, b)) continue;
        if (this._createsCycle(a, b)) continue;
        this.connections.push({
          in_node: a, out_node: b,
          weight: rng.uniform(-cfg.weight_init_range, cfg.weight_init_range),
          enabled: true,
          innovation: tracker.innovationFor(a, b),
        });
        return;
      }
    }
  }

  private _addNode(rng: SeededRNG, tracker: InnovationTracker): void {
    const enabled = this.connections.filter(c => c.enabled);
    if (enabled.length === 0) return;

    const conn = rng.pick(enabled);
    conn.enabled = false;

    const newId = tracker.nextNodeId();
    this.nodes.push({ id: newId, type: NodeType.HIDDEN });

    // in → new (weight 1.0, canonical NEAT split)
    this.connections.push({
      in_node: conn.in_node, out_node: newId,
      weight: 1.0, enabled: true,
      innovation: tracker.innovationFor(conn.in_node, newId),
    });
    // new → out (inherits original weight)
    this.connections.push({
      in_node: newId, out_node: conn.out_node,
      weight: conn.weight, enabled: true,
      innovation: tracker.innovationFor(newId, conn.out_node),
    });
  }

  private _removeConnection(rng: SeededRNG): void {
    if (this.connections.length === 0) return;

    // Prefer removing disabled connections (cleanup)
    const disabled = this.connections.filter(c => !c.enabled);
    if (disabled.length > 0 && rng.next() < 0.7) {
      const conn = rng.pick(disabled);
      this.connections = this.connections.filter(c => c !== conn);
      return;
    }

    // Output protection: never disconnect the last enabled incoming connection per output
    const outputIds = this.outputIds;
    const enabledCount = new Map<number, number>();
    for (const oid of outputIds) enabledCount.set(oid, 0);
    for (const c of this.connections) {
      if (c.enabled) {
        const cnt = enabledCount.get(c.out_node);
        if (cnt !== undefined) enabledCount.set(c.out_node, cnt + 1);
      }
    }

    const enabled = this.connections.filter(c => c.enabled);
    if (enabled.length <= this._numOutputs) return; // safety floor

    const safe = enabled.filter(c => {
      const cnt = enabledCount.get(c.out_node);
      return cnt !== undefined && cnt > 1;
    });

    if (safe.length > 0) {
      const conn = rng.pick(safe);
      this.connections = this.connections.filter(c => c !== conn);
    }
    // If no safe candidate, do nothing (output protection)
  }

  private _removeNode(rng: SeededRNG): void {
    const hidden = this.hiddenIds;
    if (hidden.length === 0) return;

    const nodeId = rng.pick(hidden);

    // Output protection: check each output still has ≥1 enabled incoming after removal
    const outputIds = this.outputIds;
    const remainingCount = new Map<number, number>();
    for (const oid of outputIds) remainingCount.set(oid, 0);
    for (const c of this.connections) {
      if (c.enabled && c.in_node !== nodeId && c.out_node !== nodeId) {
        const cnt = remainingCount.get(c.out_node);
        if (cnt !== undefined) remainingCount.set(c.out_node, cnt + 1);
      }
    }
    for (const oid of outputIds) {
      if ((remainingCount.get(oid) || 0) === 0) return; // cancel
    }

    this.nodes = this.nodes.filter(n => n.id !== nodeId);
    this.connections = this.connections.filter(c => c.in_node !== nodeId && c.out_node !== nodeId);
  }

  /** TS innovation: toggle enabled/disabled with output protection */
  private _toggleConnections(cfg: GenomeConfig, rng: SeededRNG): void {
    const outputIds = this.outputIds;
    const enabledCount = new Map<number, number>();
    for (const oid of outputIds) enabledCount.set(oid, 0);
    for (const c of this.connections) {
      if (c.enabled) {
        const cnt = enabledCount.get(c.out_node);
        if (cnt !== undefined) enabledCount.set(c.out_node, cnt + 1);
      }
    }

    for (const conn of this.connections) {
      if (rng.next() < cfg.connection_toggle_rate) {
        if (conn.enabled) {
          // Disabling: output protection
          const cnt = enabledCount.get(conn.out_node);
          if (cnt !== undefined && cnt <= 1) continue;
          conn.enabled = false;
          enabledCount.set(conn.out_node, (cnt || 1) - 1);
        } else {
          // Re-enabling: must check for cycles AND output protection is not needed
          if (this._createsCycle(conn.in_node, conn.out_node)) continue;
          conn.enabled = true;
        }
      }
    }
  }

  // ── Helpers ──────────────────────────────────────────────

  private _edgeExists(inNode: number, outNode: number): boolean {
    return this.connections.some(c => c.in_node === inNode && c.out_node === outNode);
  }

  /** DFS cycle check: would adding inNode→outNode create a cycle? */
  private _createsCycle(inNode: number, outNode: number): boolean {
    const adj = new Map<number, number[]>();
    for (const n of this.nodes) adj.set(n.id, []);
    for (const c of this.connections) {
      if (c.enabled) {
        const list = adj.get(c.in_node)!;
        list.push(c.out_node);
      }
    }

    const visited = new Set<number>();
    const stack = [outNode];
    while (stack.length > 0) {
      const current = stack.pop()!;
      if (current === inNode) return true;
      if (visited.has(current)) continue;
      visited.add(current);
      const neighbors = adj.get(current);
      if (neighbors) {
        for (const n of neighbors) stack.push(n);
      }
    }
    return false;
  }
}