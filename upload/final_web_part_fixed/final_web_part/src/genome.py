"""
src/genome.py — Représentation génomique, mutations, crossover, innovation counter,
compatibilité distance, sérialisation JSON.
"""

from __future__ import annotations

import copy
import json
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ═══════════════════════════════════════════════════════════════════════
#  Innovation counter (global, auto-incrémenté)
# ═══════════════════════════════════════════════════════════════════════

class InnovationCounter:
    """Compteur global auto-incrémenté pour les IDs d'innovation."""

    _instance: InnovationCounter | None = None
    _value: int = 0

    def __new__(cls) -> InnovationCounter:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def next_id(self) -> int:
        self._value += 1
        return self._value

    @property
    def current(self) -> int:
        return self._value

    def reset(self) -> None:
        self._value = 0


# ═══════════════════════════════════════════════════════════════════════
#  NodeGene / ConnectionGene
# ═══════════════════════════════════════════════════════════════════════

class NodeType(Enum):
    INPUT = "INPUT"
    HIDDEN = "HIDDEN"
    OUTPUT = "OUTPUT"


@dataclass
class NodeGene:
    id: int
    type: NodeType
    activation: str = "tanh"


@dataclass
class ConnectionGene:
    in_node_id: int
    out_node_id: int
    weight: float
    enabled: bool = True
    innovation_id: int = 0

    def key(self) -> tuple[int, int]:
        return (self.in_node_id, self.out_node_id)


# ═══════════════════════════════════════════════════════════════════════
#  Genome
# ═══════════════════════════════════════════════════════════════════════

class Genome:
    """
    Génome encodant un réseau de neurones feedforward (DAG).
    Initial fully connected, poids ∈ [-1, 1].
    Supporte crossover et mutations NEAT.
    """

    def __init__(
        self,
        num_inputs: int,
        num_outputs: int,
        rng: random.Random | None = None,
    ) -> None:
        self.num_inputs = num_inputs
        self.num_outputs = num_outputs
        self._rng = rng or random.Random()
        
        self.ray_range = self._rng.uniform(50.0, 300.0)

        self.nodes: dict[int, NodeGene] = {}
        self.connections: dict[tuple[int, int], ConnectionGene] = {}
        self._next_hidden_id: int = num_inputs + num_outputs
        
        self._build_fully_connected()

    # ── Bootstrap : fully connected ──────────────────────────────────

    def _build_fully_connected(self) -> None:
        """Crée le génome initial : fully connected, poids ∈ [-1, 1]."""
        for i in range(self.num_inputs):
            self.nodes[i] = NodeGene(id=i, type=NodeType.INPUT)

        for i in range(self.num_outputs):
            oid = self.num_inputs + i
            self.nodes[oid] = NodeGene(id=oid, type=NodeType.OUTPUT)

        ic = InnovationCounter()
        for i in range(self.num_inputs):
            for j in range(self.num_outputs):
                oid = self.num_inputs + j
                key = (i, oid)
                w = self._rng.uniform(-1.0, 1.0)
                self.connections[key] = ConnectionGene(
                    in_node_id=i,
                    out_node_id=oid,
                    weight=w,
                    enabled=True,
                    innovation_id=ic.next_id,
                )

    # ── Propriétés dérivées ──────────────────────────────────────────

    @property
    def input_ids(self) -> list[int]:
        return [n.id for n in self.nodes.values() if n.type == NodeType.INPUT]

    @property
    def output_ids(self) -> list[int]:
        return [n.id for n in self.nodes.values() if n.type == NodeType.OUTPUT]

    @property
    def hidden_ids(self) -> list[int]:
        return [n.id for n in self.nodes.values() if n.type == NodeType.HIDDEN]

    @property
    def enabled_connections(self) -> list[ConnectionGene]:
        return [c for c in self.connections.values() if c.enabled]

    @property
    def connection_count(self) -> int:
        return sum(1 for c in self.connections.values() if c.enabled)

    @property
    def max_innovation(self) -> int:
        """Innovation ID maximale dans ce génome."""
        if not self.connections:
            return 0
        return max(c.innovation_id for c in self.connections.values())

    # ── Deep copy ────────────────────────────────────────────────────

    def deep_copy(self) -> Genome:
        """Clone profond du génome."""
        g = Genome.__new__(Genome)
        g.num_inputs = self.num_inputs
        g.num_outputs = self.num_outputs
        g._rng = self._rng
        g._next_hidden_id = self._next_hidden_id
        g.ray_range = self.ray_range

        g.nodes = {nid: NodeGene(n.id, n.type, n.activation) for nid, n in self.nodes.items()}
        g.connections = {
            k: ConnectionGene(c.in_node_id, c.out_node_id, c.weight, c.enabled, c.innovation_id)
            for k, c in self.connections.items()
        }
        return g

    # ══════════════════════════════════════════════════════════════════
    #  CROSSOVER  (NEAT — alignement par innovation number)
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    def crossover(
        parent1: Genome,
        parent2: Genome,
        fitness1: float,
        fitness2: float,
        cfg: Any,
        rng: random.Random,
    ) -> Genome:
        """
        Crossover NEAT entre deux génomes.
        - Gènes matching (même innovation_id) : hérité aléatoirement d'un parent
        - Gènes excess/disjoint : hérités du parent le plus fit
        - Si fitness égale : hérités aléatoirement
        """
        if fitness1 >= fitness2:
            dominant, recessive = parent1, parent2
        else:
            dominant, recessive = parent2, parent1

        # Construire le mapping innovation → connection pour chaque parent
        dom_genes: dict[int, ConnectionGene] = {c.innovation_id: c for c in dominant.connections.values()}
        rec_genes: dict[int, ConnectionGene] = {c.innovation_id: c for c in recessive.connections.values()}

        all_innovations = sorted(set(dom_genes.keys()) | set(rec_genes.keys()))
        if not all_innovations:
            # Fallback : clone du dominant
            return dominant.deep_copy()

        child = Genome.__new__(Genome)
        child.num_inputs = dominant.num_inputs
        child.num_outputs = dominant.num_outputs
        child._rng = rng
        child.connections = {}

        # Hériter les noeuds du parent dominant (tous les noeuds existants)
        child.nodes = {nid: NodeGene(n.id, n.type, n.activation) for nid, n in dominant.nodes.items()}

        # Trouver le max hidden id pour continuer la numérotation
        child._next_hidden_id = dominant._next_hidden_id
        # Aussi vérifier le recessive
        hidden_ids = [n.id for n in child.nodes.values() if n.type == NodeType.HIDDEN]
        if hidden_ids:
            child._next_hidden_id = max(child._next_hidden_id, max(hidden_ids) + 1)

        for inn_id in all_innovations:
            in_dom = inn_id in dom_genes
            in_rec = inn_id in rec_genes

            if in_dom and in_rec:
                # Gène matching : choisir aléatoirement
                if rng.random() < 0.5:
                    gene = dom_genes[inn_id]
                else:
                    gene = rec_genes[inn_id]
                # Average weights occasionally (25% chance)
                if rng.random() < 0.25:
                    gene = ConnectionGene(
                        in_node_id=gene.in_node_id,
                        out_node_id=gene.out_node_id,
                        weight=(dom_genes[inn_id].weight + rec_genes[inn_id].weight) / 2.0,
                        enabled=gene.enabled,
                        innovation_id=gene.innovation_id,
                    )
            elif in_dom:
                # Excess/disjoint du dominant → toujours hérité
                gene = dom_genes[inn_id]
                # S'assurer que les noeuds référencés existent
                if gene.in_node_id not in child.nodes:
                    parent_node = recessive.nodes.get(gene.in_node_id, dominant.nodes.get(gene.in_node_id))
                    if parent_node:
                        child.nodes[gene.in_node_id] = NodeGene(parent_node.id, parent_node.type, parent_node.activation)
                if gene.out_node_id not in child.nodes:
                    parent_node = recessive.nodes.get(gene.out_node_id, dominant.nodes.get(gene.out_node_id))
                    if parent_node:
                        child.nodes[gene.out_node_id] = NodeGene(parent_node.id, parent_node.type, parent_node.activation)
            else:
                # Excess/disjoint du récessif → hérité seulement si même fitness (rare)
                if abs(fitness1 - fitness2) < 0.01 and rng.random() < 0.5:
                    gene = rec_genes[inn_id]
                    if gene.in_node_id not in child.nodes:
                        parent_node = recessive.nodes.get(gene.in_node_id)
                        if parent_node:
                            child.nodes[gene.in_node_id] = NodeGene(parent_node.id, parent_node.type, parent_node.activation)
                    if gene.out_node_id not in child.nodes:
                        parent_node = recessive.nodes.get(gene.out_node_id)
                        if parent_node:
                            child.nodes[gene.out_node_id] = NodeGene(parent_node.id, parent_node.type, parent_node.activation)
                else:
                    continue  # Skip recessive's excess/disjoint

            child.connections[gene.key()] = gene

        # Hériter le ray_range (moyenne ou du dominant)
        if rng.random() < 0.5:
            child.ray_range = dominant.ray_range
        else:
            child.ray_range = recessive.ray_range
        # Petite mutation du ray_range
        child.ray_range += rng.gauss(0, 10.0)
        child.ray_range = max(20.0, min(child.ray_range, 500.0))

        return child

    # ══════════════════════════════════════════════════════════════════
    #  COMPATIBILITY DISTANCE  (pour spéciation)
    # ══════════════════════════════════════════════════════════════════

    def compatibility_distance(self, other: Genome, cfg: Any) -> float:
        """
        Calcule la distance de compatibilité NEAT entre deux génomes.
        δ = c1·E/N + c2·D/N + c3·ΔW̄
        E = gènes excess, D = gènes disjoint, N = gènes du plus grand, ΔW̄ = diff poids moyenne.
        """
        innovations1 = {c.innovation_id: c for c in self.connections.values()}
        innovations2 = {c.innovation_id: c for c in other.connections.values()}

        all_ids = sorted(set(innovations1.keys()) | set(innovations2.keys()))
        if not all_ids:
            return 0.0

        n = max(len(innovations1), len(innovations2))
        if n == 0:
            n = 1

        max_inn = max(all_ids)
        matching_weights_diff = []
        excess = 0
        disjoint = 0

        for inn_id in all_ids:
            in1 = inn_id in innovations1
            in2 = inn_id in innovations2

            if in1 and in2:
                # Matching gene
                matching_weights_diff.append(abs(innovations1[inn_id].weight - innovations2[inn_id].weight))
            elif in1 and inn_id < max_inn:
                disjoint += 1
            elif in2 and inn_id < max_inn:
                disjoint += 1
            else:
                # Un des deux a ce gene et c'est le max → excess
                excess += 1

        avg_weight_diff = sum(matching_weights_diff) / len(matching_weights_diff) if matching_weights_diff else 0.0

        c1 = cfg.compatibility_excess_coeff
        c2 = cfg.compatibility_disjoint_coeff
        c3 = cfg.compatibility_weight_coeff

        delta = c1 * excess / n + c2 * disjoint / n + c3 * avg_weight_diff
        return delta

    # ══════════════════════════════════════════════════════════════════
    #  MUTATIONS
    # ══════════════════════════════════════════════════════════════════

    def mutate(self, cfg) -> None:
        """Applique les mutations stochastiques au génome."""
        rng = self._rng

        # 1. Mutation de poids
        if rng.random() < cfg.mutate_weights_prob:
            self._mutate_weights(cfg)

        # 2. Ajouter une connexion
        if rng.random() < cfg.add_connection_prob:
            self._mutate_add_connection()

        # 3. Ajouter un nœud
        if rng.random() < cfg.add_node_prob:
            self._mutate_add_node()

        # 4. Retirer une connexion
        if rng.random() < cfg.remove_connection_prob:
            self._mutate_remove_connection()

        # 5. Retirer un nœud hidden
        if rng.random() < cfg.remove_node_prob:
            self._mutate_remove_node()

        # 6. Toggle connexion
        self._mutate_toggle_connections()

    def _mutate_weights(self, cfg) -> None:
        """Perturbe ou réinitialise chaque poids."""
        rng = self._rng
        for conn in self.connections.values():
            r = rng.random()
            if r < cfg.weight_perturb_prob:
                conn.weight += rng.gauss(0, cfg.weight_sigma)
            elif r < cfg.weight_perturb_prob + cfg.weight_reset_prob:
                conn.weight = rng.uniform(-1.0, 1.0)
                
        if rng.random() < cfg.weight_perturb_prob:
            self.ray_range += rng.gauss(0, 15.0)
            self.ray_range = max(20.0, min(self.ray_range, 500.0))

    def _mutate_add_connection(self) -> None:
        """Relie deux nœuds non connectés. Vérification DAG."""
        rng = self._rng
        all_ids = list(self.nodes.keys())

        for _ in range(10):
            a, b = rng.sample(all_ids, 2)
            if self.nodes[b].type == NodeType.INPUT:
                continue
            key_ab = (a, b)
            key_ba = (b, a)
            if key_ab not in self.connections and key_ba not in self.connections:
                if not self._would_create_cycle(a, b):
                    ic = InnovationCounter()
                    self.connections[key_ab] = ConnectionGene(
                        in_node_id=a,
                        out_node_id=b,
                        weight=rng.uniform(-1.0, 1.0),
                        enabled=True,
                        innovation_id=ic.next_id,
                    )
                    return
                elif not self._would_create_cycle(b, a):
                    ic = InnovationCounter()
                    self.connections[key_ba] = ConnectionGene(
                        in_node_id=b,
                        out_node_id=a,
                        weight=rng.uniform(-1.0, 1.0),
                        enabled=True,
                        innovation_id=ic.next_id,
                    )
                    return

    def _mutate_add_node(self) -> None:
        """Coupe une connexion existante, insère un nœud hidden."""
        enabled = [c for c in self.connections.values() if c.enabled]
        if not enabled:
            return

        rng = self._rng
        conn = rng.choice(enabled)
        conn.enabled = False

        new_id = self._next_hidden_id
        self._next_hidden_id += 1
        self.nodes[new_id] = NodeGene(id=new_id, type=NodeType.HIDDEN)

        ic = InnovationCounter()

        key_in = (conn.in_node_id, new_id)
        self.connections[key_in] = ConnectionGene(
            in_node_id=conn.in_node_id,
            out_node_id=new_id,
            weight=1.0,
            enabled=True,
            innovation_id=ic.next_id,
        )

        key_out = (new_id, conn.out_node_id)
        self.connections[key_out] = ConnectionGene(
            in_node_id=new_id,
            out_node_id=conn.out_node_id,
            weight=conn.weight,
            enabled=True,
            innovation_id=ic.next_id,
        )

    def _mutate_remove_connection(self) -> None:
        """Retire une connexion. Priorité aux connexions disabled."""
        rng = self._rng

        disabled = [c for c in self.connections.values() if not c.enabled]
        if disabled and rng.random() < 0.7:
            conn = rng.choice(disabled)
            del self.connections[conn.key()]
            return

        enabled = [c for c in self.connections.values() if c.enabled]
        if len(enabled) <= self.num_outputs:  # Garder au moins les sorties
            return
        conn = rng.choice(enabled)
        del self.connections[conn.key()]

    def _mutate_remove_node(self) -> None:
        """Retire un nœud hidden et toutes ses connexions."""
        hidden = self.hidden_ids
        if not hidden:
            return

        rng = self._rng
        node_id = rng.choice(hidden)
        del self.nodes[node_id]

        keys_to_remove = [k for k in self.connections if node_id in k]
        for k in keys_to_remove:
            del self.connections[k]

    def _mutate_toggle_connections(self) -> None:
        """Active ou désactive une connexion."""
        rng = self._rng
        for conn in self.connections.values():
            if rng.random() < 0.02:
                conn.enabled = not conn.enabled

    # ── Vérification de cycle (DFS) ──────────────────────────────────

    def _would_create_cycle(self, from_id: int, to_id: int) -> bool:
        visited: set[int] = set()
        stack = [to_id]

        adj: dict[int, list[int]] = {nid: [] for nid in self.nodes}
        for c in self.connections.values():
            if c.enabled:
                adj.setdefault(c.in_node_id, []).append(c.out_node_id)

        while stack:
            current = stack.pop()
            if current == from_id:
                return True
            if current in visited:
                continue
            visited.add(current)
            for neighbor in adj.get(current, []):
                stack.append(neighbor)

        return False

    # ══════════════════════════════════════════════════════════════════
    #  SÉRIALISATION JSON
    # ══════════════════════════════════════════════════════════════════

    def to_dict(self) -> dict[str, Any]:
        return {
            "num_inputs": self.num_inputs,
            "num_outputs": self.num_outputs,
            "next_hidden_id": self._next_hidden_id,
            "ray_range": self.ray_range,
            "nodes": [
                {"id": n.id, "type": n.type.value, "activation": n.activation}
                for n in self.nodes.values()
            ],
            "connections": [
                {
                    "in": c.in_node_id,
                    "out": c.out_node_id,
                    "weight": c.weight,
                    "enabled": c.enabled,
                    "innovation_id": c.innovation_id,
                }
                for c in self.connections.values()
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Genome:
        g = cls.__new__(Genome)
        g.num_inputs = data["num_inputs"]
        g.num_outputs = data["num_outputs"]
        g._next_hidden_id = data.get("next_hidden_id", g.num_inputs + g.num_outputs)
        g._rng = random.Random()

        g.ray_range = data.get("ray_range", 150.0)

        g.nodes = {}
        for nd in data["nodes"]:
            g.nodes[nd["id"]] = NodeGene(
                id=nd["id"],
                type=NodeType(nd["type"]),
                activation=nd.get("activation", "tanh"),
            )

        g.connections = {}
        for cd in data["connections"]:
            key = (cd["in"], cd["out"])
            g.connections[key] = ConnectionGene(
                in_node_id=cd["in"],
                out_node_id=cd["out"],
                weight=cd["weight"],
                enabled=cd["enabled"],
                innovation_id=cd.get("innovation_id", 0),
            )

        if g.connections:
            max_inn = max(c.innovation_id for c in g.connections.values())
            ic = InnovationCounter()
            if max_inn >= ic.current:
                ic._value = max_inn

        return g

    @classmethod
    def from_json(cls, json_str: str) -> Genome:
        return cls.from_dict(json.loads(json_str))