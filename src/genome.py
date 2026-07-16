"""Genome representation: a fixed-topology weight vector (poc3).

Unlike the NEAT-style variable topology this replaces (poc2.x), the network
SHAPE is fixed at construction time — derived from ``NetworkConfig`` (never
hardcoded, invariant n°1), identical for every genome in a run. Only weights
evolve: there is no structural mutation, no innovation numbers, no cycle
detection (a fixed stack of layers cannot form a cycle by construction).

Every genome sharing a config shares the exact same ``layer_shapes``, which
is what lets ``src.network.batch_activate`` stack a whole population into one
tensor and run its forward pass in a single batched NumPy call.

Invariants honoured here:
- No magic numbers: every rate/range comes from :class:`GenomeConfig`; shape
  comes from :func:`network_layer_shapes`.
- Determinism: every stochastic operation takes an injected ``random.Random``.
"""

from __future__ import annotations

import json
from random import Random
from typing import Any

import numpy as np

from src.config import GenomeConfig, NetworkConfig


def network_layer_shapes(network: NetworkConfig) -> list[tuple[int, int]]:
    """Derive the fixed per-layer ``(in, out)`` shapes from ``NetworkConfig``.

    ``network.hidden_size`` (0 by default, poc3 v1) controls the topology:
    ``0`` -> a single linear layer ``[(num_inputs, num_outputs)]`` (the
    lowest-capacity shape, matching the near-zero hidden-node count the
    previous NEAT encoding averaged after tens of thousands of ticks); ``>0``
    -> two layers, ``[(num_inputs, hidden_size), (hidden_size, num_outputs)]``.
    """
    if network.hidden_size > 0:
        return [
            (network.num_inputs, network.hidden_size),
            (network.hidden_size, network.num_outputs),
        ]
    return [(network.num_inputs, network.num_outputs)]


class Genome:
    """A fixed-topology neural-network genome: one flat vector of weights."""

    def __init__(
        self, layer_shapes: list[tuple[int, int]], weights: np.ndarray
    ) -> None:
        self.layer_shapes = layer_shapes
        self.weights = weights  # flat float64 array, len == sum(in*out)

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    @classmethod
    def new_random(
        cls, config: GenomeConfig, layer_shapes: list[tuple[int, int]], rng: Random
    ) -> "Genome":
        """Create a founder genome: every weight drawn uniformly at random."""
        total = sum(in_ * out for in_, out in layer_shapes)
        weights = np.array(
            [
                rng.uniform(-config.weight_init_range, config.weight_init_range)
                for _ in range(total)
            ],
            dtype=np.float64,
        )
        return cls(list(layer_shapes), weights)

    def clone(self) -> "Genome":
        """Return a deep, independent copy of this genome."""
        return Genome(list(self.layer_shapes), self.weights.copy())

    def matrices(self) -> list[np.ndarray]:
        """Reshape the flat weight vector into one ``(in, out)`` matrix per layer."""
        matrices = []
        offset = 0
        for in_, out in self.layer_shapes:
            size = in_ * out
            matrices.append(self.weights[offset : offset + size].reshape(in_, out))
            offset += size
        return matrices

    @staticmethod
    def crossover(fitter: "Genome", other: "Genome", rng: Random) -> "Genome":
        """Element-wise crossover: each weight independently from either parent.

        Both parents share ``layer_shapes`` by construction (fixed topology),
        so alignment is trivial — unlike NEAT, no innovation numbers are
        needed to know which weight corresponds to which.
        """
        weights = np.empty_like(fitter.weights)
        for i in range(weights.size):
            weights[i] = fitter.weights[i] if rng.random() < 0.5 else other.weights[i]
        return Genome(list(fitter.layer_shapes), weights)

    # ------------------------------------------------------------------ #
    # Mutation
    # ------------------------------------------------------------------ #
    def mutate(self, config: GenomeConfig, rng: Random) -> None:
        """Perturb each weight independently; clamp to ±weight_max (anti-saturation)."""
        for i in range(self.weights.size):
            if rng.random() < config.weight_mutation_rate:
                self.weights[i] += rng.gauss(0.0, config.weight_perturbation)
        np.clip(self.weights, -config.weight_max, config.weight_max, out=self.weights)

    # ------------------------------------------------------------------ #
    # Serialisation
    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict[str, Any]:
        """Serialise the genome to a plain, JSON-ready dict."""
        return {
            "layer_shapes": [list(shape) for shape in self.layer_shapes],
            "weights": self.weights.tolist(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Genome":
        """Rebuild a genome from a dict produced by :meth:`to_dict`."""
        layer_shapes = [tuple(shape) for shape in data["layer_shapes"]]
        weights = np.array(data["weights"], dtype=np.float64)
        return cls(layer_shapes, weights)

    def to_json(self) -> str:
        """Serialise the genome to a JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, text: str) -> "Genome":
        """Rebuild a genome from a JSON string."""
        return cls.from_dict(json.loads(text))
