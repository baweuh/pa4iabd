"""Neural network evaluation from a fixed-topology Genome (poc3).

Invariants honoured here:
- Feedforward guaranteed by construction: layers apply in series, so no
  cycle is possible — no DFS check is needed (CLAUDE.md invariant n°3).
- No topological sort or per-agent cache is needed either (invariant n°4):
  the evaluation order is fixed by ``genome.layer_shapes`` itself.
- Hidden layers use the configured activation (tanh); the FINAL layer stays
  linear — ``Agent.decide`` applies tanh explicitly to bound speed and turn
  (invariant n°5), exactly as under the previous NEAT encoding.
"""

from __future__ import annotations

from typing import Callable, Sequence

import numpy as np

from src.config import NetworkConfig
from src.genome import Genome

_ACTIVATIONS: dict[str, Callable[[np.ndarray], np.ndarray]] = {
    "tanh": np.tanh,
}


def _get_activation(name: str) -> Callable[[np.ndarray], np.ndarray]:
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
        self._matrices = genome.matrices()
        self.input_ids: list[int] = list(range(genome.layer_shapes[0][0]))
        self.output_ids: list[int] = list(range(genome.layer_shapes[-1][1]))

    def activate(self, inputs: Sequence[float]) -> tuple[float, ...]:
        """Run a forward pass; return one raw (linear) value per output.

        For an agent's own network this is always ``(vx_raw, vy_raw)`` (2
        outputs, per invariant n°5).
        """
        if len(inputs) != len(self.input_ids):
            raise ValueError(
                f"expected {len(self.input_ids)} inputs, got {len(inputs)}"
            )
        values = np.array(inputs, dtype=np.float64)
        last = len(self._matrices) - 1
        for i, matrix in enumerate(self._matrices):
            values = values @ matrix
            if i < last:
                values = self._activation(values)
        return tuple(values.tolist())


def batch_activate(
    genomes: Sequence[Genome], batch_senses: np.ndarray, config: NetworkConfig
) -> np.ndarray:
    """Run the forward pass for a WHOLE population in one batched NumPy call.

    ``genomes`` must all share the same ``layer_shapes`` — guaranteed by
    construction (poc3 has no structural mutation, every genome in a run is
    built from the same :func:`src.genome.network_layer_shapes`). Their
    per-layer matrices are stacked into a ``(pop, in, out)`` tensor and
    multiplied against ``batch_senses`` (``(pop, num_inputs)``) with one
    ``einsum`` per layer — this is the batched replacement for calling
    ``NeuralNetwork.activate()`` once per agent (the forward-pass bottleneck
    identified in the poc2.4 perf audit: heterogeneous NEAT topologies could
    never be stacked this way).

    Returns ``(pop, num_outputs)`` raw (linear) values — same contract as
    :meth:`NeuralNetwork.activate`, tanh applied by the caller.
    """
    count = len(genomes)
    if count == 0:
        return np.empty((0, config.num_outputs), dtype=np.float64)

    activation = _get_activation(config.activation)
    num_layers = len(genomes[0].layer_shapes)
    values = np.asarray(batch_senses, dtype=np.float64)
    for layer in range(num_layers):
        stacked = np.stack(
            [g.matrices()[layer] for g in genomes], axis=0
        )  # (pop, in, out)
        values = np.einsum("pi,pio->po", values, stacked)
        if layer < num_layers - 1:
            values = activation(values)
    return values
