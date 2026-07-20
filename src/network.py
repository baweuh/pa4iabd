"""Neural network evaluation built from a Genome (NEAT-style, feedforward only).

Invariants honoured here:
- Topological sort computed ONCE at __init__, never recomputed (CLAUDE.md n°4).
- Hidden nodes use the configured activation (tanh); output nodes are linear.
- Disabled connections are ignored everywhere (genome.py may leave them in place
  after add_node splits an edge).

Under ``hebbian.enabled`` the compiled weights are no longer frozen for the
agent's life: ``apply_hebbian`` adjusts them from the last forward pass (see
that method). The TOPOLOGY still never changes, so invariant n°4's cached
topological sort stays valid — only the weight copies move, and only in the
compiled network, never in the genome.
"""

from __future__ import annotations

import heapq
import math
from typing import Callable, Sequence

from src.config import HebbianConfig, NetworkConfig
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

    def __init__(
        self,
        genome: Genome,
        config: NetworkConfig,
        hebbian: HebbianConfig | None = None,
    ) -> None:
        self._activation = _get_activation(config.activation)
        # Plasticity is opt-in and costs the legacy path nothing: with it off,
        # activate() never records activations and the weights stay exactly the
        # frozen copies taken from the genome below.
        self._hebbian = hebbian if hebbian is not None and hebbian.enabled else None
        # Activations of the most recent activate(), kept only under plasticity
        # so apply_hebbian() can use the SAME tick's pre/postsynaptic values.
        self._last_values: dict[int, float] | None = None

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

        if self._hebbian is not None:
            self._last_values = values

        return tuple(values[nid] for nid in self.output_ids)

    def apply_hebbian(self, reward: float) -> None:
        """Reward-modulated Hebbian update on the last forward pass.

        ``dw = learning_rate * reward * x * y`` for every enabled connection,
        clamped to ``+/- hebbian.weight_max``. No-op when plasticity is off,
        when ``reward`` is zero (the rule is reward-gated), or before the first
        :meth:`activate`.

        Deliberately NOT called from :meth:`activate`. Several callers activate
        a network purely to measure it — ``diagnostics.steer_score``, the
        novelty ``behavior_descriptor``, the HyperNEAT CPPN queries — and
        observing an agent must never modify its brain. Only ``Agent.eat``,
        which knows the tick's real reward, drives learning.

        Mutates the compiled network's own weight copies, never the genome:
        learning is non-Lamarckian, children inherit the innate wiring.
        """
        if self._hebbian is None or reward == 0.0 or self._last_values is None:
            return
        values = self._last_values
        step = self._hebbian.learning_rate * reward
        limit = self._hebbian.weight_max
        for nid, srcs in self._incoming.items():
            if not srcs:
                continue
            post = values[nid]
            if self._node_type[nid] == OUTPUT:
                # Output nodes are linear (unbounded), but what the node
                # actually EMITS is tanh(total) — Agent.decide applies it before
                # using the value. Learning on the raw sum would let one
                # saturated output dominate every update and would make
                # learning_rate uninterpretable; on the emitted value both
                # x and y are in (-1, 1), so one apple moves a weight by at
                # most learning_rate.
                post = math.tanh(post)
            self._incoming[nid] = [
                (src, max(-limit, min(limit, w + step * values[src] * post)))
                for src, w in srcs
            ]
