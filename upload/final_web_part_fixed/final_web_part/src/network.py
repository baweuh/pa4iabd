"""
src/network.py — Construction du réseau depuis le génome, tri topologique (cache),
forward pass NumPy. CDC §2.4.
"""

from __future__ import annotations

import numpy as np

from .genome import Genome, NodeType, NodeGene


def _activation_fn(name: str):
    """Retourne la fonction d'activation numpy correspondant au nom."""
    if name == "tanh":
        return np.tanh
    elif name == "sigmoid":
        return lambda x: 1.0 / (1.0 + np.exp(-np.clip(x, -500, 500)))
    else:
        return np.tanh  # fallback


class NeuralNetwork:
    """
    Réseau de neurones feedforward (DAG) construit depuis un Genome.
    - Tri topologique calculé UNE FOIS à la création et mis en cache.
    - Activation : tanh sur les nœuds hidden et output (paramétrable par nœud).
    - Forward pass vectorisé avec NumPy.
    """

    def __init__(self, genome: Genome) -> None:
        self.genome = genome
        self._cached_order: list[int] | None = None
        self._cached_weights: list[tuple[int, int, float]] | None = None
        self._cached_activations: dict[int, callable] = {}
        self._build()

    def _build(self) -> None:
        """Construit le réseau : tri topologique + préparation des poids."""
        g = self.genome

        # Calculer le tri topologique
        order = self._topological_sort()
        self._cached_order = order

        # Index des inputs et outputs
        self._input_ids = sorted(g.input_ids)
        self._output_ids = sorted(g.output_ids)

        # Préparer les connexions enabled : (in_idx_in_order, out_idx_in_order, weight)
        idx_map = {nid: i for i, nid in enumerate(order)}
        self._conn_list: list[tuple[int, int, float]] = []
        for conn in g.enabled_connections:
            if conn.in_node_id in idx_map and conn.out_node_id in idx_map:
                self._conn_list.append((
                    idx_map[conn.in_node_id],
                    idx_map[conn.out_node_id],
                    conn.weight,
                ))

        # Préparer les fonctions d'activation par nœud
        self._cached_activations = {
            nid: _activation_fn(node.activation) if node.type != NodeType.INPUT else lambda x: x
            for nid, node in g.nodes.items()
        }

        # Masques pour input/output dans le tableau d'activation
        self._input_positions = [idx_map[nid] for nid in self._input_ids if nid in idx_map]
        self._output_positions = [idx_map[nid] for nid in self._output_ids if nid in idx_map]

    def _topological_sort(self) -> list[int]:
        """Tri topologique via Kahn's algorithm. Vérifie l'absence de cycles."""
        g = self.genome
        in_degree: dict[int, int] = {nid: 0 for nid in g.nodes}
        adj: dict[int, list[int]] = {nid: [] for nid in g.nodes}

        for conn in g.enabled_connections:
            if conn.in_node_id in g.nodes and conn.out_node_id in g.nodes:
                adj[conn.in_node_id].append(conn.out_node_id)
                in_degree[conn.out_node_id] += 1

        # File : nœuds avec in_degree == 0
        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        queue.sort()  # ordre déterministe
        order: list[int] = []

        while queue:
            node = queue.pop(0)
            order.append(node)
            for neighbor in sorted(adj[node]):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
                    queue.sort()

        if len(order) != len(g.nodes):
            raise ValueError("Cycle détecté dans le génome — pas un DAG valide.")

        return order

    def activate(self, inputs: np.ndarray) -> np.ndarray:
        """
        Forward pass. inputs = array numpy de taille num_inputs.
        Retourne un array numpy de taille num_outputs.
        """
        n = len(self._cached_order)
        activations = np.zeros(n, dtype=np.float64)

        # Injecter les inputs
        for i, pos in enumerate(self._input_positions):
            if i < len(inputs):
                activations[pos] = inputs[i]

        # Propager dans l'ordre topologique
        for conn_in, conn_out, weight in self._conn_list:
            activations[conn_out] += weight * activations[conn_in]

        # Appliquer les activations (sauf inputs)
        for nid, pos in [(nid, i) for i, nid in enumerate(self._cached_order)]:
            node = self.genome.nodes.get(nid)
            if node is not None and node.type != NodeType.INPUT:
                fn = self._cached_activations.get(nid, np.tanh)
                activations[pos] = fn(activations[pos])

        # Extraire les outputs
        return np.array([activations[pos] for pos in self._output_positions])

    @property
    def network_size(self) -> int:
        """Nombre de connexions actives (pour métriques)."""
        return len(self._conn_list)