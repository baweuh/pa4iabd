"""Genome representation and mutation operators (NEAT-style, feedforward only).

A genome is a list of :class:`NodeGene` and :class:`ConnectionGene`. It carries
no neural-network logic (that lives in ``network.py``); it is a pure data
structure plus the five mutation operators required by the project.

Invariants honoured here:
- Networks stay strictly feedforward: :meth:`Genome.add_connection` runs a DFS
  cycle check before inserting an edge (CLAUDE.md invariant n°3).
- No magic numbers: every rate / range comes from :class:`GenomeConfig`.
- Determinism: every stochastic operation takes an injected ``random.Random``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from random import Random
from typing import Any

from src.config import GenomeConfig

INPUT = "input"
HIDDEN = "hidden"
OUTPUT = "output"


@dataclass
class NodeGene:
    """A single neuron. ``node_type`` is one of input/hidden/output."""

    node_id: int
    node_type: str


@dataclass
class ConnectionGene:
    """A directed, weighted edge between two nodes."""

    in_node: int
    out_node: int
    weight: float
    enabled: bool
    innovation: int


class InnovationTracker:
    """Global allocator for unique hidden-node ids and innovation numbers.

    Structural mutations that are *identical* (same ``in_node``/``out_node``
    pair) receive the same innovation number, mirroring standard NEAT so that
    genome alignment would remain possible if crossover is added later.
    """

    def __init__(self) -> None:
        self._node_counter = 0
        self._innovation_counter = 0
        self._edge_innovations: dict[tuple[int, int], int] = {}

    def bump_node_floor(self, floor: int) -> None:
        """Ensure subsequently allocated node ids are >= ``floor``."""
        self._node_counter = max(self._node_counter, floor)

    def next_node_id(self) -> int:
        """Allocate and return the next unique node id."""
        node_id = self._node_counter
        self._node_counter += 1
        return node_id

    def innovation_for(self, in_node: int, out_node: int) -> int:
        """Return the innovation number for an edge, creating it if needed."""
        key = (in_node, out_node)
        if key not in self._edge_innovations:
            self._edge_innovations[key] = self._innovation_counter
            self._innovation_counter += 1
        return self._edge_innovations[key]

    def reset(self) -> None:
        """Reset all counters. Intended for deterministic tests."""
        self._node_counter = 0
        self._innovation_counter = 0
        self._edge_innovations.clear()


# Module-level default tracker (the "global innovation counter").
TRACKER = InnovationTracker()


class Genome:
    """A feedforward neural-network genome with mutation operators."""

    def __init__(
        self,
        nodes: list[NodeGene],
        connections: list[ConnectionGene],
    ) -> None:
        self.nodes = nodes
        self.connections = connections

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    @classmethod
    def new_fully_connected(
        cls,
        config: GenomeConfig,
        num_inputs: int,
        num_outputs: int,
        rng: Random,
        tracker: InnovationTracker = TRACKER,
    ) -> "Genome":
        """Create a genome with every input wired to every output.

        Input ids are ``0..num_inputs-1``; output ids follow them. Hidden node
        ids (allocated later by :meth:`add_node`) start above the reserved
        input/output range.
        """
        tracker.bump_node_floor(num_inputs + num_outputs)
        nodes = [NodeGene(i, INPUT) for i in range(num_inputs)]
        nodes += [NodeGene(num_inputs + j, OUTPUT) for j in range(num_outputs)]
        connections: list[ConnectionGene] = []
        for i in range(num_inputs):
            for j in range(num_inputs, num_inputs + num_outputs):
                connections.append(
                    ConnectionGene(
                        in_node=i,
                        out_node=j,
                        weight=_random_weight(config, rng),
                        enabled=True,
                        innovation=tracker.innovation_for(i, j),
                    )
                )
        return cls(nodes, connections)

    @staticmethod
    def crossover(fitter: "Genome", other: "Genome", rng: Random) -> "Genome":
        """Produce a feedforward child genome by NEAT-style crossover.

        Connection genes are aligned by innovation number. Matching genes (present
        in both parents) are inherited from a random parent; disjoint/excess genes
        are inherited from the ``fitter`` parent only (canonical NEAT). Node genes
        follow the connections they support, plus every input/output node.

        The child is guaranteed strictly feedforward (invariant n°3): inherited
        edges are added in innovation order and any edge that would close a cycle
        against the edges already accepted is skipped.
        """
        picks = Genome._align_genes(fitter, other, rng)

        # Node lookup: fitter's node types win on overlap (its structure is kept).
        node_by_id: dict[int, str] = {}
        for parent in (other, fitter):
            for node in parent.nodes:
                node_by_id[node.node_id] = node.node_type

        child = Genome(nodes=[], connections=[])
        # Same-class construction helper; pylint over-flags the static→instance hop.
        child._inherit(picks, node_by_id)  # pylint: disable=protected-access
        return child

    @staticmethod
    def _align_genes(
        fitter: "Genome", other: "Genome", rng: Random
    ) -> list[ConnectionGene]:
        """Align connection genes by innovation for :meth:`crossover`.

        Matching genes are drawn from a random parent; disjoint/excess genes are
        kept from ``fitter`` only and dropped from ``other`` (canonical NEAT).
        """
        by_innov_f = {c.innovation: c for c in fitter.connections}
        by_innov_o = {c.innovation: c for c in other.connections}
        picks: list[ConnectionGene] = []
        for innov in sorted(set(by_innov_f) | set(by_innov_o)):
            if innov in by_innov_f and innov in by_innov_o:
                picks.append(
                    by_innov_f[innov] if rng.random() < 0.5 else by_innov_o[innov]
                )
            elif innov in by_innov_f:
                picks.append(by_innov_f[innov])  # disjoint/excess from fitter
        return picks

    def _inherit(self, picks: list[ConnectionGene], node_by_id: dict[int, str]) -> None:
        """Populate this empty genome with inherited I/O nodes and edges.

        Every input/output node is always present — the network needs the full
        I/O vector even if a node ends up unconnected. Edges are added in
        innovation order; any edge closing a cycle is skipped (invariant n°3).
        """
        for nid, ntype in node_by_id.items():
            if ntype != HIDDEN:
                self.nodes.append(NodeGene(nid, ntype))
        present_ids = {n.node_id for n in self.nodes}

        def _ensure_node(nid: int) -> bool:
            if nid in present_ids:
                return True
            ntype = node_by_id.get(nid)
            if ntype is None:
                return False
            self.nodes.append(NodeGene(nid, ntype))
            present_ids.add(nid)
            return True

        for gene in picks:
            if not (_ensure_node(gene.in_node) and _ensure_node(gene.out_node)):
                continue
            if gene.enabled and self._creates_cycle(gene.in_node, gene.out_node):
                continue
            self.connections.append(
                ConnectionGene(
                    gene.in_node,
                    gene.out_node,
                    gene.weight,
                    gene.enabled,
                    gene.innovation,
                )
            )

    def clone(self) -> "Genome":
        """Return a deep, independent copy of this genome."""
        return Genome(
            nodes=[NodeGene(n.node_id, n.node_type) for n in self.nodes],
            connections=[
                ConnectionGene(c.in_node, c.out_node, c.weight, c.enabled, c.innovation)
                for c in self.connections
            ],
        )

    # ------------------------------------------------------------------ #
    # Serialisation
    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict[str, Any]:
        """Serialise the genome to a plain, JSON-ready dict."""
        return {
            "nodes": [{"id": n.node_id, "type": n.node_type} for n in self.nodes],
            "connections": [
                {
                    "in": c.in_node,
                    "out": c.out_node,
                    "weight": c.weight,
                    "enabled": c.enabled,
                    "innovation": c.innovation,
                }
                for c in self.connections
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Genome":
        """Rebuild a genome from a dict produced by :meth:`to_dict`."""
        nodes = [NodeGene(n["id"], n["type"]) for n in data["nodes"]]
        connections = [
            ConnectionGene(
                c["in"], c["out"], c["weight"], c["enabled"], c["innovation"]
            )
            for c in data["connections"]
        ]
        return cls(nodes, connections)

    def to_json(self) -> str:
        """Serialise the genome to a JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, text: str) -> "Genome":
        """Rebuild a genome from a JSON string."""
        return cls.from_dict(json.loads(text))

    # ------------------------------------------------------------------ #
    # Mutation
    # ------------------------------------------------------------------ #
    def mutate(
        self,
        config: GenomeConfig,
        rng: Random,
        tracker: InnovationTracker = TRACKER,
    ) -> None:
        """Apply all mutation operators according to their configured rates."""
        self.mutate_weights(config, rng)
        if rng.random() < config.add_connection_rate:
            self.add_connection(config, rng, tracker)
        if rng.random() < config.add_node_rate:
            self.add_node(config, rng, tracker)
        if rng.random() < config.remove_connection_rate:
            self.remove_connection(rng)
        if rng.random() < config.remove_node_rate:
            self.remove_node(rng)

    def mutate_weights(self, config: GenomeConfig, rng: Random) -> None:
        """Perturb each connection weight; clamp to ±weight_max (anti-saturation)."""
        for conn in self.connections:
            if rng.random() < config.weight_mutation_rate:
                conn.weight += rng.gauss(0.0, config.weight_perturbation)
                w = config.weight_max
                conn.weight = max(-w, min(w, conn.weight))

    def add_connection(
        self,
        config: GenomeConfig,
        rng: Random,
        tracker: InnovationTracker = TRACKER,
    ) -> bool:
        """Add one feedforward connection between two unconnected nodes.

        Picks a source (input/hidden) and target (hidden/output). If the chosen
        direction would create a cycle, tries the reverse direction; if both
        are invalid, abandons the mutation (CLAUDE.md invariant n°3).
        """
        sources = [n for n in self.nodes if n.node_type != OUTPUT]
        targets = [n for n in self.nodes if n.node_type != INPUT]
        if not sources or not targets:
            return False

        src = rng.choice(sources)
        dst = rng.choice(targets)
        if src.node_id == dst.node_id:
            return False

        for a, b in ((src.node_id, dst.node_id), (dst.node_id, src.node_id)):
            if not self._is_valid_edge(a, b):
                continue
            if self._creates_cycle(a, b):
                continue
            self.connections.append(
                ConnectionGene(
                    in_node=a,
                    out_node=b,
                    weight=_random_weight(config, rng),
                    enabled=True,
                    innovation=tracker.innovation_for(a, b),
                )
            )
            return True
        return False

    def add_node(
        self,
        config: GenomeConfig,
        rng: Random,
        tracker: InnovationTracker = TRACKER,
    ) -> bool:
        """Split an enabled connection by inserting a new hidden node.

        The original edge is disabled; ``in -> new`` gets weight 1.0 and
        ``new -> out`` inherits the original weight (classic NEAT split).
        """
        _ = config  # kept for signature symmetry; split weights are canonical.
        enabled = [c for c in self.connections if c.enabled]
        if not enabled:
            return False
        conn = rng.choice(enabled)
        conn.enabled = False

        new_id = tracker.next_node_id()
        self.nodes.append(NodeGene(new_id, HIDDEN))
        self.connections.append(
            ConnectionGene(
                in_node=conn.in_node,
                out_node=new_id,
                weight=1.0,
                enabled=True,
                innovation=tracker.innovation_for(conn.in_node, new_id),
            )
        )
        self.connections.append(
            ConnectionGene(
                in_node=new_id,
                out_node=conn.out_node,
                weight=conn.weight,
                enabled=True,
                innovation=tracker.innovation_for(new_id, conn.out_node),
            )
        )
        return True

    def remove_connection(self, rng: Random) -> bool:
        """Remove one randomly chosen connection."""
        if not self.connections:
            return False
        conn = rng.choice(self.connections)
        self.connections.remove(conn)
        return True

    def remove_node(self, rng: Random) -> bool:
        """Remove a random hidden node together with its incident edges."""
        hidden = [n for n in self.nodes if n.node_type == HIDDEN]
        if not hidden:
            return False
        node = rng.choice(hidden)
        self.nodes.remove(node)
        self.connections = [
            c for c in self.connections if node.node_id not in (c.in_node, c.out_node)
        ]
        return True

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _is_valid_edge(self, in_node: int, out_node: int) -> bool:
        """An edge is valid if endpoints differ and it doesn't already exist."""
        if in_node == out_node:
            return False
        return not any(
            c.in_node == in_node and c.out_node == out_node for c in self.connections
        )

    def _creates_cycle(self, in_node: int, out_node: int) -> bool:
        """Return True if adding ``in_node -> out_node`` would create a cycle.

        A cycle appears iff ``out_node`` can already reach ``in_node`` through
        enabled connections.
        """
        adjacency: dict[int, list[int]] = {}
        for conn in self.connections:
            if conn.enabled:
                adjacency.setdefault(conn.in_node, []).append(conn.out_node)

        stack = [out_node]
        visited: set[int] = set()
        while stack:
            current = stack.pop()
            if current == in_node:
                return True
            if current in visited:
                continue
            visited.add(current)
            stack.extend(adjacency.get(current, ()))
        return False


def _random_weight(config: GenomeConfig, rng: Random) -> float:
    return rng.uniform(-config.weight_init_range, config.weight_init_range)
