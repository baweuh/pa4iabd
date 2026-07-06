// ═══════════════════════════════════════════════════════════
//  genome.ts — NEAT Genome: nodes, connections, mutations, crossover
//  Porté de src/genome.py
// ═══════════════════════════════════════════════════════════

import type { MutationsConfig, NeatConfig } from './config';

// ── Enums ──────────────────────────────────────────────────

export enum NodeType {
  INPUT = 'INPUT',
  HIDDEN = 'HIDDEN',
  OUTPUT = 'OUTPUT',
}

// ── Gene types ─────────────────────────────────────────────

export interface NodeGene {
  id: number;
  type: NodeType;
  activation: string;
}

export interface ConnectionGene {
  in_node_id: number;
  out_node_id: number;
  weight: number;
  enabled: boolean;
  innovation_id: number;
}

// ── Innovation Counter (singleton) ────────────────────────

class InnovationCounterClass {
  private static instance: InnovationCounterClass;
  private value = 0;

  private constructor() {}

  static getInstance(): InnovationCounterClass {
    if (!InnovationCounterClass.instance) {
      InnovationCounterClass.instance = new InnovationCounterClass();
    }
    return InnovationCounterClass.instance;
  }

  get nextId(): number {
    this.value += 1;
    return this.value;
  }

  get current(): number {
    return this.value;
  }

  reset(): void {
    this.value = 0;
  }

  syncTo(value: number): void {
    if (value >= this.value) {
      this.value = value;
    }
  }
}

export const InnovationCounter = InnovationCounterClass.getInstance;

// ── Seeded PRNG (Mulberry32) ─────────────────────────────

export class SeededRNG {
  private state: number;

  constructor(seed: number) {
    this.state = seed;
  }

  /** Returns float in [0, 1) */
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

  /** Pick random element from array */
  pick<T>(arr: T[]): T {
    return arr[this.int(arr.length)];
  }

  /** Pick N random elements (without replacement) */
  sample<T>(arr: T[], n: number): T[] {
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

// ── Genome ────────────────────────────────────────────────

export class Genome {
  num_inputs: number;
  num_outputs: number;
  nodes: Map<number, NodeGene> = new Map();
  connections: Map<string, ConnectionGene> = new Map();
  private _nextHiddenId: number;
  ray_range: number;
  private _rng: SeededRNG;

  constructor(num_inputs: number, num_outputs: number, rng: SeededRNG) {
    this.num_inputs = num_inputs;
    this.num_outputs = num_outputs;
    this._rng = rng;
    this._nextHiddenId = num_inputs + num_outputs;
    this.ray_range = rng.uniform(50, 300);
    this._buildFullyConnected();
  }

  private _buildFullyConnected(): void {
    for (let i = 0; i < this.num_inputs; i++) {
      this.nodes.set(i, { id: i, type: NodeType.INPUT, activation: 'tanh' });
    }
    for (let i = 0; i < this.num_outputs; i++) {
      const oid = this.num_inputs + i;
      this.nodes.set(oid, { id: oid, type: NodeType.OUTPUT, activation: 'tanh' });
    }
    const ic = InnovationCounter();
    for (let i = 0; i < this.num_inputs; i++) {
      for (let j = 0; j < this.num_outputs; j++) {
        const oid = this.num_inputs + j;
        this.connections.set(`${i},${oid}`, {
          in_node_id: i,
          out_node_id: oid,
          weight: this._rng.uniform(-1, 1),
          enabled: true,
          innovation_id: ic.nextId,
        });
      }
    }
  }

  get inputIds(): number[] {
    return [...this.nodes.values()].filter(n => n.type === NodeType.INPUT).map(n => n.id).sort((a, b) => a - b);
  }

  get outputIds(): number[] {
    return [...this.nodes.values()].filter(n => n.type === NodeType.OUTPUT).map(n => n.id).sort((a, b) => a - b);
  }

  get hiddenIds(): number[] {
    return [...this.nodes.values()].filter(n => n.type === NodeType.HIDDEN).map(n => n.id);
  }

  get enabledConnections(): ConnectionGene[] {
    return [...this.connections.values()].filter(c => c.enabled);
  }

  get connectionCount(): number {
    return [...this.connections.values()].filter(c => c.enabled).length;
  }

  get maxInnovation(): number {
    const conns = [...this.connections.values()];
    if (conns.length === 0) return 0;
    return Math.max(...conns.map(c => c.innovation_id));
  }

  connKey(inId: number, outId: number): string {
    return `${inId},${outId}`;
  }

  deepCopy(): Genome {
    const g = Object.create(Genome.prototype) as Genome;
    g.num_inputs = this.num_inputs;
    g.num_outputs = this.num_outputs;
    g._rng = this._rng;
    g._nextHiddenId = this._nextHiddenId;
    g.ray_range = this.ray_range;
    g.nodes = new Map();
    for (const [id, n] of this.nodes) {
      g.nodes.set(id, { ...n });
    }
    g.connections = new Map();
    for (const [k, c] of this.connections) {
      g.connections.set(k, { ...c });
    }
    return g;
  }

  // ── Crossover (NEAT — aligned by innovation number) ──

  static crossover(
    parent1: Genome,
    parent2: Genome,
    fitness1: number,
    fitness2: number,
    cfg: NeatConfig,
    rng: SeededRNG,
  ): Genome {
    const dominant = fitness1 >= fitness2 ? parent1 : parent2;
    const recessive = fitness1 >= fitness2 ? parent2 : parent1;

    const domGenes = new Map<number, ConnectionGene>();
    for (const c of dominant.connections.values()) domGenes.set(c.innovation_id, c);
    const recGenes = new Map<number, ConnectionGene>();
    for (const c of recessive.connections.values()) recGenes.set(c.innovation_id, c);

    const allInnovations = new Set([...domGenes.keys(), ...recGenes.keys()]);
    const sorted = [...allInnovations].sort((a, b) => a - b);
    if (sorted.length === 0) return dominant.deepCopy();

    const child = Object.create(Genome.prototype) as Genome;
    child.num_inputs = dominant.num_inputs;
    child.num_outputs = dominant.num_outputs;
    child._rng = rng;
    child.connections = new Map();

    // Inherit all nodes from dominant
    child.nodes = new Map();
    for (const [id, n] of dominant.nodes) {
      child.nodes.set(id, { ...n });
    }
    child._nextHiddenId = dominant._nextHiddenId;

    // Also add recessive nodes that might be referenced
    for (const [id, n] of recessive.nodes) {
      if (!child.nodes.has(id)) child.nodes.set(id, { ...n });
    }
    const hiddenIds = [...child.nodes.values()].filter(n => n.type === NodeType.HIDDEN).map(n => n.id);
    if (hiddenIds.length > 0) {
      child._nextHiddenId = Math.max(child._nextHiddenId, Math.max(...hiddenIds) + 1);
    }

    for (const innId of sorted) {
      const inDom = domGenes.has(innId);
      const inRec = recGenes.has(innId);

      if (inDom && inRec) {
        let gene: ConnectionGene;
        if (rng.next() < 0.5) {
          gene = { ...domGenes.get(innId)! };
        } else {
          gene = { ...recGenes.get(innId)! };
        }
        // Average weights 25% of the time
        if (rng.next() < 0.25) {
          gene.weight = (domGenes.get(innId)!.weight + recGenes.get(innId)!.weight) / 2;
        }
        child.connections.set(child.connKey(gene.in_node_id, gene.out_node_id), gene);
      } else if (inDom) {
        const gene = { ...domGenes.get(innId)! };
        if (!child.nodes.has(gene.in_node_id)) {
          const src = recessive.nodes.get(gene.in_node_id) || dominant.nodes.get(gene.in_node_id);
          if (src) child.nodes.set(gene.in_node_id, { ...src });
        }
        if (!child.nodes.has(gene.out_node_id)) {
          const src = recessive.nodes.get(gene.out_node_id) || dominant.nodes.get(gene.out_node_id);
          if (src) child.nodes.set(gene.out_node_id, { ...src });
        }
        child.connections.set(child.connKey(gene.in_node_id, gene.out_node_id), gene);
      } else {
        // Recessive excess/disjoint — only if same fitness
        if (Math.abs(fitness1 - fitness2) < 0.01 && rng.next() < 0.5) {
          const gene = { ...recGenes.get(innId)! };
          if (!child.nodes.has(gene.in_node_id)) {
            const src = recessive.nodes.get(gene.in_node_id);
            if (src) child.nodes.set(gene.in_node_id, { ...src });
          }
          if (!child.nodes.has(gene.out_node_id)) {
            const src = recessive.nodes.get(gene.out_node_id);
            if (src) child.nodes.set(gene.out_node_id, { ...src });
          }
          child.connections.set(child.connKey(gene.in_node_id, gene.out_node_id), gene);
        }
      }
    }

    // Inherit ray_range
    child.ray_range = rng.next() < 0.5 ? dominant.ray_range : recessive.ray_range;
    child.ray_range += rng.gauss(0, 10);
    child.ray_range = Math.max(20, Math.min(child.ray_range, 500));

    return child;
  }

  // ── Compatibility Distance ──

  compatibilityDistance(other: Genome, cfg: NeatConfig): number {
    const inn1 = new Map<number, ConnectionGene>();
    for (const c of this.connections.values()) inn1.set(c.innovation_id, c);
    const inn2 = new Map<number, ConnectionGene>();
    for (const c of other.connections.values()) inn2.set(c.innovation_id, c);

    const allIds = new Set([...inn1.keys(), ...inn2.keys()]);
    if (allIds.size === 0) return 0;

    const n = Math.max(inn1.size, inn2.size) || 1;
    const maxInn = Math.max(...allIds);

    let matchingWeightDiff = 0;
    let matchCount = 0;
    let excess = 0;
    let disjoint = 0;

    for (const innId of allIds) {
      const in1 = inn1.has(innId);
      const in2 = inn2.has(innId);
      if (in1 && in2) {
        matchingWeightDiff += Math.abs(inn1.get(innId)!.weight - inn2.get(innId)!.weight);
        matchCount++;
      } else if (innId < maxInn) {
        disjoint++;
      } else {
        excess++;
      }
    }

    const avgWeightDiff = matchCount > 0 ? matchingWeightDiff / matchCount : 0;
    return (
      cfg.compatibility_excess_coeff * (excess / n) +
      cfg.compatibility_disjoint_coeff * (disjoint / n) +
      cfg.compatibility_weight_coeff * avgWeightDiff
    );
  }

  // ── Mutations ──

  mutate(cfg: MutationsConfig): void {
    const rng = this._rng;
    if (rng.next() < cfg.mutate_weights_prob) this._mutateWeights(cfg);
    if (rng.next() < cfg.add_connection_prob) this._mutateAddConnection();
    if (rng.next() < cfg.add_node_prob) this._mutateAddNode();
    if (rng.next() < cfg.remove_connection_prob) this._mutateRemoveConnection();
    if (rng.next() < cfg.remove_node_prob) this._mutateRemoveNode();
    this._mutateToggleConnections();
  }

  private _mutateWeights(cfg: MutationsConfig): void {
    const rng = this._rng;
    for (const conn of this.connections.values()) {
      const r = rng.next();
      if (r < cfg.weight_perturb_prob) {
        conn.weight += rng.gauss(0, cfg.weight_sigma);
      } else if (r < cfg.weight_perturb_prob + cfg.weight_reset_prob) {
        conn.weight = rng.uniform(-1, 1);
      }
    }
    if (rng.next() < cfg.weight_perturb_prob) {
      this.ray_range += rng.gauss(0, 15);
      this.ray_range = Math.max(20, Math.min(this.ray_range, 500));
    }
  }

  private _mutateAddConnection(): void {
    const rng = this._rng;
    const allIds = [...this.nodes.keys()];
    for (let attempt = 0; attempt < 10; attempt++) {
      const [a, b] = rng.sample(allIds, 2);
      const nodeB = this.nodes.get(b)!;
      if (nodeB.type === NodeType.INPUT) continue;

      const keyAB = this.connKey(a, b);
      const keyBA = this.connKey(b, a);

      if (!this.connections.has(keyAB) && !this.connections.has(keyBA)) {
        const ic = InnovationCounter();
        if (!this._wouldCreateCycle(a, b)) {
          this.connections.set(keyAB, {
            in_node_id: a, out_node_id: b,
            weight: rng.uniform(-1, 1), enabled: true, innovation_id: ic.nextId,
          });
          return;
        } else if (!this._wouldCreateCycle(b, a)) {
          this.connections.set(keyBA, {
            in_node_id: b, out_node_id: a,
            weight: rng.uniform(-1, 1), enabled: true, innovation_id: ic.nextId,
          });
          return;
        }
      }
    }
  }

  private _mutateAddNode(): void {
    const enabled = this.enabledConnections;
    if (enabled.length === 0) return;

    const rng = this._rng;
    const conn = rng.pick(enabled);
    const connKey = this.connKey(conn.in_node_id, conn.out_node_id);
    conn.enabled = false;

    const newId = this._nextHiddenId++;
    this.nodes.set(newId, { id: newId, type: NodeType.HIDDEN, activation: 'tanh' });

    const ic = InnovationCounter();
    this.connections.set(this.connKey(conn.in_node_id, newId), {
      in_node_id: conn.in_node_id, out_node_id: newId,
      weight: 1.0, enabled: true, innovation_id: ic.nextId,
    });
    this.connections.set(this.connKey(newId, conn.out_node_id), {
      in_node_id: newId, out_node_id: conn.out_node_id,
      weight: conn.weight, enabled: true, innovation_id: ic.nextId,
    });
  }

  private _mutateRemoveConnection(): void {
    const rng = this._rng;
    const disabled = [...this.connections.values()].filter(c => !c.enabled);
    if (disabled.length > 0 && rng.next() < 0.7) {
      const conn = rng.pick(disabled);
      this.connections.delete(this.connKey(conn.in_node_id, conn.out_node_id));
      return;
    }
    const enabled = this.enabledConnections;
    if (enabled.length <= this.num_outputs) return;
    const conn = rng.pick(enabled);
    this.connections.delete(this.connKey(conn.in_node_id, conn.out_node_id));
  }

  private _mutateRemoveNode(): void {
    const hidden = this.hiddenIds;
    if (hidden.length === 0) return;

    const rng = this._rng;
    const nodeId = rng.pick(hidden);
    this.nodes.delete(nodeId);
    for (const [key] of this.connections) {
      const [a, b] = key.split(',').map(Number);
      if (a === nodeId || b === nodeId) this.connections.delete(key);
    }
  }

  private _mutateToggleConnections(): void {
    const rng = this._rng;
    for (const conn of this.connections.values()) {
      if (rng.next() < 0.02) conn.enabled = !conn.enabled;
    }
  }

  // ── Cycle detection (DFS) ──

  private _wouldCreateCycle(fromId: number, toId: number): boolean {
    const visited = new Set<number>();
    const stack = [toId];

    // Build adjacency list
    const adj = new Map<number, number[]>();
    for (const nid of this.nodes.keys()) adj.set(nid, []);
    for (const c of this.connections.values()) {
      if (c.enabled) {
        const list = adj.get(c.in_node_id) || [];
        list.push(c.out_node_id);
        adj.set(c.in_node_id, list);
      }
    }

    while (stack.length > 0) {
      const current = stack.pop()!;
      if (current === fromId) return true;
      if (visited.has(current)) continue;
      visited.add(current);
      for (const neighbor of (adj.get(current) || [])) {
        stack.push(neighbor);
      }
    }
    return false;
  }
}