"""Indirect encoding: derive a substrate network's weights from a CPPN.

HyperNEAT MVP (research-roadmap item #4, docs/DESIGN-hyperneat-mvp.md).
Instead of a genome directly wiring the sensor→output network, it wires a
small CPPN (Compositional Pattern-Producing Network): a plain feedforward
``Genome``/``NeuralNetwork`` (same class, same mutation operators, same
``InnovationTracker`` — no new machinery) that maps a pair of substrate-node
coordinates to a connection weight. The substrate itself is FIXED (no
structural mutation, no hidden layer for this MVP): every sensor input is
wired straight to every output, exactly like a ``initial_connectivity=1.0``
founder genome, except the weight comes from querying the CPPN instead of
being drawn at random.

Substrate coordinates:
- Sensor inputs sit on the unit circle at their ray's egocentric angle
  (``src.geometry.ray_angles``, same angles perception itself uses), one
  ``z`` value per channel "kind" (apple_dist/wall_dist/apple_flag/wall_flag
  or the combined variant, plus energy/proprioception/apples_in_view),
  evenly spaced in [-1, 1] so the CPPN can tell channels apart. Scalar
  (non-ray) inputs sit at the ring's centre (0, 0) with their own z.
- The 2 outputs (speed, turn) have no inherent geometry; they get two fixed
  points clearly outside the ring (y = -1.5) so they are never mistaken for
  a sensor coordinate.

Deliberately out of scope for this MVP (see docs/DESIGN-hyperneat-mvp.md):
a hidden substrate layer, per-node CPPN activation functions (sin/gaussian),
a link-expression threshold (sparsity), and a distance input to the CPPN.
"""

from __future__ import annotations

import math

from src.config import HyperNEATConfig, NetworkConfig, SensorConfig
from src.genome import (
    INPUT,
    OUTPUT,
    ConnectionGene,
    Genome,
    InnovationTracker,
    NodeGene,
)
from src.geometry import ray_angles
from src.network import NeuralNetwork

# CPPN query: (x, y, z) for each of the two queried substrate nodes.
CPPN_NUM_INPUTS = 6
# CPPN answer: one raw connection weight (squashed and scaled by the caller).
CPPN_NUM_OUTPUTS = 1

# Fixed, off-ring coordinates for the 2 substrate outputs (speed, turn) — see
# module docstring. y = -1.5 keeps them clear of the unit-circle ring (radius
# 1) and the scalar inputs' centre point (0, 0).
_OUTPUT_COORDS: tuple[tuple[float, float, float], ...] = (
    (-0.5, -1.5, 0.0),
    (0.5, -1.5, 0.0),
)


def substrate_input_coords(sensors: SensorConfig) -> list[tuple[float, float, float]]:
    """Return one ``(x, y, z)`` per substrate input, in ``Agent.sense()`` order.

    Length always equals ``sensors.num_inputs`` — every sensor toggle
    combination is supported, not just the 49-input default (invariant n°1:
    the layout is derived from config, never hardcoded). Ring channels (one
    per ray, per "kind": apple_dist/wall_dist/apple_flag/wall_flag, or
    dist/apple_flag/wall_flag when ``split_distance`` is off) come first,
    matching ``Agent.sense()``'s column order exactly; scalar channels
    (energy, then proprioception/apples_in_view if enabled) follow.
    """
    ring_kinds = (
        ["apple_dist", "wall_dist", "apple_flag", "wall_flag"]
        if sensors.split_distance
        else ["dist", "apple_flag", "wall_flag"]
    )
    scalar_kinds = ["energy"]
    if sensors.proprioception:
        scalar_kinds.append("actual_speed")
    if sensors.apples_in_view:
        scalar_kinds.append("apples_in_view")

    kinds = ring_kinds + scalar_kinds
    n_kinds = len(kinds)
    z_of = {
        kind: (2.0 * i / (n_kinds - 1) - 1.0) if n_kinds > 1 else 0.0
        for i, kind in enumerate(kinds)
    }

    angles = ray_angles(sensors.num_rays, sensors.fov, heading=0.0)
    coords: list[tuple[float, float, float]] = []
    for kind in ring_kinds:
        z = z_of[kind]
        coords.extend((math.cos(a), math.sin(a), z) for a in angles)
    for kind in scalar_kinds:
        coords.append((0.0, 0.0, z_of[kind]))
    return coords


def build_substrate_genome(
    cppn_net: NeuralNetwork, sensors: SensorConfig, hyperneat_config: HyperNEATConfig
) -> Genome:
    """Query ``cppn_net`` for every (input, output) pair to build a dense substrate.

    The substrate is a fresh, throwaway ``Genome`` (never mutated or evolved
    itself — it is fully rebuilt from the CPPN for every agent) with the same
    node-id convention as ``Genome.new_fully_connected``: inputs ``0..N-1``,
    outputs ``N..N+1``. A local ``InnovationTracker`` is enough since these
    innovation numbers are never compared against another genome's.
    """
    input_coords = substrate_input_coords(sensors)
    num_inputs = len(input_coords)
    num_outputs = len(_OUTPUT_COORDS)

    nodes = [NodeGene(i, INPUT) for i in range(num_inputs)]
    nodes += [NodeGene(num_inputs + j, OUTPUT) for j in range(num_outputs)]

    tracker = InnovationTracker()
    connections: list[ConnectionGene] = []
    for i, (x1, y1, z1) in enumerate(input_coords):
        for j, (x2, y2, z2) in enumerate(_OUTPUT_COORDS):
            raw_weight = cppn_net.activate([x1, y1, z1, x2, y2, z2])[0]
            weight = math.tanh(raw_weight) * hyperneat_config.weight_scale
            out_id = num_inputs + j
            connections.append(
                ConnectionGene(
                    in_node=i,
                    out_node=out_id,
                    weight=weight,
                    enabled=True,
                    innovation=tracker.innovation_for(i, out_id),
                )
            )
    return Genome(nodes, connections)


def build_substrate_network(
    cppn_genome: Genome,
    sensors: SensorConfig,
    network_config: NetworkConfig,
    hyperneat_config: HyperNEATConfig,
) -> NeuralNetwork:
    """Build the executable substrate network an agent actually runs.

    ``cppn_genome`` is evolved normally (mutation/crossover/speciation all
    operate on it exactly as on a direct-encoding genome). ``network_config``
    is reused as-is for both the CPPN and the substrate — ``NeuralNetwork``
    only reads its ``activation`` field, deriving input/output node ids from
    the genome itself, so no separate config type is needed for the CPPN's
    different (6 -> 1) shape.
    """
    cppn_net = NeuralNetwork(cppn_genome, network_config)
    substrate_genome = build_substrate_genome(cppn_net, sensors, hyperneat_config)
    return NeuralNetwork(substrate_genome, network_config)
