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
BIAS = "bias"  # always-on founder source (value 1.0); never a mutation target


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
        """Create a founder genome wiring inputs (+ optional bias) to outputs.

        Input ids are ``0..num_inputs-1``; output ids follow them; the bias
        node (if ``config.bias_enabled``) takes the single id right after the
        outputs. Hidden node ids (allocated later by :meth:`add_node`) start
        above this reserved range.

        ``config.genome.initial_connectivity`` (default 1.0) controls how much
        of the full source×output bipartite graph is wired at genesis (sources
        = inputs, plus the bias node when enabled): 1.0 wires every source to
        every output (legacy, exact original behaviour when bias is off);
        lower values wire each output to a random sparse subset of sources (at
        least one, so no output stays permanently silent).
        """
        has_bias = config.bias_enabled
        bias_id = num_inputs + num_outputs
        tracker.bump_node_floor(bias_id + (1 if has_bias else 0))
        nodes = [NodeGene(i, INPUT) for i in range(num_inputs)]
        nodes += [NodeGene(num_inputs + j, OUTPUT) for j in range(num_outputs)]
        if has_bias:
            nodes.append(NodeGene(bias_id, BIAS))
        output_ids = range(num_inputs, num_inputs + num_outputs)
        num_sources = num_inputs + (1 if has_bias else 0)
        # Precompute each output's wired-source set *before* the weight-drawing
        # loop below, so the connectivity==1.0, bias-off path draws RNG in
        # exactly the original (i outer, j inner) order — byte-for-byte
        # backward compatible.
        wired: dict[int, frozenset[int]] = {
            j: frozenset(
                cls._founder_inputs_for(num_sources, config.initial_connectivity, rng)
            )
            for j in output_ids
        }
        connections: list[ConnectionGene] = []
        for i in range(num_sources):
            src_id = i if i < num_inputs else bias_id
            for j in output_ids:
                if i not in wired[j]:
                    continue
                connections.append(
                    ConnectionGene(
                        in_node=src_id,
                        out_node=j,
                        weight=_random_weight(config, rng),
                        enabled=True,
                        innovation=tracker.innovation_for(src_id, j),
                    )
                )
        return cls(nodes, connections)

    @staticmethod
    def _founder_inputs_for(
        num_sources: int, connectivity: float, rng: Random
    ) -> list[int]:
        """Source indices wired to one founder output, per ``initial_connectivity``.

        ``num_sources`` counts inputs plus the bias node when enabled (indices
        are later remapped to real node ids by the caller). ``connectivity ==
        1.0`` returns every source, consuming **no** RNG state (legacy path,
        preserves the original deterministic weight-draw order). Lower values
        sample a random subset (at least 1, at most ``num_sources``).
        """
        if connectivity >= 1.0:
            return list(range(num_sources))
        k = max(1, round(connectivity * num_sources))
        return rng.sample(range(num_sources), k)

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

        Picks a source (input/bias/hidden) and target (hidden/output). If the
        chosen direction would create a cycle, tries the reverse direction; if
        both are invalid, abandons the mutation (CLAUDE.md invariant n°3). The
        bias node is a source only — it never receives an incoming connection
        (it isn't computed from anything, it's a constant).
        """
        sources = [n for n in self.nodes if n.node_type != OUTPUT]
        targets = [n for n in self.nodes if n.node_type not in (INPUT, BIAS)]
        if not sources or not targets:
            return False

        src = rng.choice(sources)
        dst = rng.choice(targets)
        if src.node_id == dst.node_id:
            return False

        # dst is never input/bias by construction (targets excludes both), but
        # the reversed fallback direction below puts src second — guard it too,
        # so a bias/input node never ends up on the receiving end of an edge.
        node_type = {n.node_id: n.node_type for n in self.nodes}
        for a, b in ((src.node_id, dst.node_id), (dst.node_id, src.node_id)):
            if node_type[b] in (INPUT, BIAS):
                continue
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
