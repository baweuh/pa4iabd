"""Neural network evaluation built from a Genome (NEAT-style, feedforward only).

Invariants honoured here:
- Topological sort computed ONCE at __init__, never recomputed (CLAUDE.md n°4).
- Hidden nodes use the configured activation (tanh); output nodes are linear.
- Disabled connections are ignored everywhere (genome.py may leave them in place
  after add_node splits an edge).
"""

from __future__ import annotations

import heapq
import math
from typing import Callable, Sequence

from src.config import NetworkConfig
from src.genome import BIAS, INPUT, OUTPUT, Genome

_ACTIVATIONS: dict[str, Callable[[float], float]] = {
    "tanh": math.tanh,
}


def _get_activation(name: str) -> Callable[[float], float]:
    try:
        return _ACTIVATIONS[name]
    except KeyError as exc:
        raise ValueError(
            f"unknown activation '{name}'; available: {sorted(_ACTIVATIONS)}"
        ) from exc


class NeuralNetwork:
    """Compiled, executable view of a Genome.

    Build once per agent at birth; call activate() every tick.
    """

    def __init__(self, genome: Genome, config: NetworkConfig) -> None:
        self._activation = _get_activation(config.activation)

        node_type: dict[int, str] = {n.node_id: n.node_type for n in genome.nodes}

        self.input_ids: list[int] = sorted(
            n.node_id for n in genome.nodes if n.node_type == INPUT
        )
        self.output_ids: list[int] = sorted(
            n.node_id for n in genome.nodes if n.node_type == OUTPUT
        )
        self._bias_ids: list[int] = [
            n.node_id for n in genome.nodes if n.node_type == BIAS
        ]

        # Build adjacency: node_id → [(src_id, weight), ...]  (enabled only)
        incoming: dict[int, list[tuple[int, float]]] = {
            n.node_id: [] for n in genome.nodes
        }
        for conn in genome.connections:
            if conn.enabled:
                incoming[conn.out_node].append((conn.in_node, conn.weight))

        # Kahn's algorithm with a min-heap — ascending node_id order for determinism
        in_deg: dict[int, int] = {nid: len(srcs) for nid, srcs in incoming.items()}
        heap: list[int] = [nid for nid, d in in_deg.items() if d == 0]
        heapq.heapify(heap)
        # successors: node → [out_node, ...]  (enabled connections only)
        successors: dict[int, list[int]] = {n.node_id: [] for n in genome.nodes}
        for conn in genome.connections:
            if conn.enabled:
                successors[conn.in_node].append(conn.out_node)
        eval_order: list[int] = []
        while heap:
            nid = heapq.heappop(heap)
            eval_order.append(nid)
            for dst in successors[nid]:
                in_deg[dst] -= 1
                if in_deg[dst] == 0:
                    heapq.heappush(heap, dst)

        if len(eval_order) != len(genome.nodes):
            raise ValueError(
                "genome contains a cycle — feedforward invariant violated "
                f"(processed {len(eval_order)}/{len(genome.nodes)} nodes)"
            )

        self._eval_order: list[int] = eval_order
        self._node_type: dict[int, str] = node_type
        self._incoming: dict[int, list[tuple[int, float]]] = incoming

    def activate(self, inputs: Sequence[float]) -> tuple[float, ...]:
        """Run a forward pass; return one raw value per output node, in id order.

        For an agent's own network this is always ``(vx_raw, vy_raw)`` (2
        outputs, per invariant n°5) — but the class is otherwise agnostic to
        output count, which a HyperNEAT CPPN (1 output: a queried connection
        weight, see ``src.hyperneat``) relies on.
        """
        if len(inputs) != len(self.input_ids):
            raise ValueError(
                f"expected {len(self.input_ids)} inputs, got {len(inputs)}"
            )

        values: dict[int, float] = {}
        for pos, nid in enumerate(self.input_ids):
            values[nid] = float(inputs[pos])
        for nid in self._bias_ids:
            values[nid] = 1.0  # always-on, never read from the sensor vector

        for nid in self._eval_order:
            ntype = self._node_type[nid]
            if ntype in (INPUT, BIAS):
                continue  # already set above
            total = sum(w * values[src] for src, w in self._incoming[nid])
            if ntype == OUTPUT:
                values[nid] = total  # linear output
            else:  # HIDDEN
                values[nid] = self._activation(total)

        return tuple(values[nid] for nid in self.output_ids)
