"""HyperNEAT MVP fast-iteration probe: CPPN genome -> substrate -> diagnostics.

0-tick loop (~0.2ms, no Simulation) for "does my encoding produce a good
network?" — the tightest iteration loop of the HyperNEAT chantier (research-
roadmap item #4, agreed with Robin 2026-07-15 before starting implementation,
see docs/DESIGN-hyperneat-mvp.md). Builds the substrate the exact same way
``Agent.__init__`` does (``src.hyperneat.build_substrate_network``) and
reuses the existing steering/behaviour diagnostics unchanged.

Two checks specific to HyperNEAT, beyond the standard steer_score verdict:
- **Geometric regularity**: does the substrate's weight pattern vary smoothly
  across adjacent rays (the correlation HyperNEAT is meant to exploit), or is
  it as rough as a randomly-initialised direct-encoding genome? Cheap
  witness comparison, same pattern as ``tools/steer_probe.py``'s
  champion-vs-random-newborns baseline.
- **Resolution transfer**: regenerate the substrate at DOUBLE ``num_rays``
  from the SAME CPPN, without re-evolving anything, and re-measure
  steer_score. A direct-encoding genome cannot do this at all (its input
  count is fixed at birth); holding up here is a capability signature no
  reducer/additive lever has, mechanistic evidence for *why* HyperNEAT would
  or wouldn't work, not a replacement for a real 6-seed campaign verdict.

Usage: python -m tools.inspect_network <cppn_genome.json> [config.yaml]
"""

from __future__ import annotations

import dataclasses
import statistics as st
import sys
from random import Random

from src.config import SimConfig
from src.diagnostics import steer_score
from src.genome import Genome
from src.hyperneat import build_substrate_genome, build_substrate_network
from src.network import NeuralNetwork
from src.novelty import behavior_descriptor

# Random direct genomes for the regularity baseline (steer_probe.py's null
# baseline uses the same count).
_WITNESS_SAMPLES = 200


def _ring_weights(genome: Genome, output_node: int, num_rays: int) -> list[float]:
    """Weights of the first per-ray channel's edges into ``output_node``, ray-ordered.

    Works for both a HyperNEAT substrate genome and a direct-encoding
    founder genome: both number input nodes ``0..num_inputs-1`` with the
    first ``num_rays`` of them being the first per-ray sensor block
    (``Agent.sense()``'s column order, shared by ``src.hyperneat``'s
    substrate-node convention and ``Genome.new_fully_connected``).
    """
    by_edge = {(c.in_node, c.out_node): c.weight for c in genome.connections}
    return [by_edge.get((ray, output_node), 0.0) for ray in range(num_rays)]


def _circular_roughness(weights: list[float]) -> float:
    """Mean |adjacent-ray weight difference|, normalised by the weight spread.

    Low = smooth/correlated across the ring (what HyperNEAT is meant to
    produce); high = angularly uncorrelated, like independently-drawn random
    weights (what direct encoding produces, by construction).
    """
    n = len(weights)
    spread = (max(weights) - min(weights)) or 1.0
    diffs = [abs(weights[i] - weights[(i + 1) % n]) for i in range(n)]
    return st.mean(diffs) / spread


def main(argv: list[str]) -> int:
    genome_path = argv[1]
    config_path = argv[2] if len(argv) > 2 else "config/default.yaml"
    cfg = SimConfig.from_yaml(config_path)

    with open(genome_path, encoding="utf-8") as f:
        cppn_genome = Genome.from_json(f.read())

    cppn_net = NeuralNetwork(cppn_genome, cfg.network)
    substrate_genome = build_substrate_genome(cppn_net, cfg.sensors, cfg.hyperneat)
    substrate_net = NeuralNetwork(substrate_genome, cfg.network)
    score = steer_score(substrate_net, cfg.sensors)
    descriptor = behavior_descriptor(substrate_net, cfg.sensors)

    cppn_hidden = sum(1 for n in cppn_genome.nodes if n.node_type == "hidden")
    cppn_enabled = sum(1 for c in cppn_genome.connections if c.enabled)
    weights = [c.weight for c in substrate_genome.connections]  # dense/enabled

    print(
        f"CPPN: {len(cppn_genome.nodes)} nodes ({cppn_hidden} hidden), "
        f"{cppn_enabled}/{len(cppn_genome.connections)} connections enabled"
    )
    print(
        f"Substrate: {len(weights)} weights, "
        f"mean {st.mean(weights):+.3f}  stdev {st.pstdev(weights):.3f}  "
        f"range [{min(weights):+.3f}, {max(weights):+.3f}]"
    )
    print(f"steer_score: {score:+.3f}")
    print(
        f"behavior_descriptor (turn response, {len(descriptor)} rays): "
        f"mean |.|={st.mean(abs(v) for v in descriptor):.3f}"
    )

    _report_regularity(cfg, substrate_genome)
    _report_resolution_transfer(cfg, cppn_genome, score)
    return 0


def _report_regularity(cfg: SimConfig, substrate_genome: Genome) -> None:
    num_inputs = cfg.sensors.num_inputs
    output_node = num_inputs  # first output ("speed"); arbitrary but fixed pick
    cppn_roughness = _circular_roughness(
        _ring_weights(substrate_genome, output_node, cfg.sensors.num_rays)
    )

    rng = Random(1234)
    witness_roughness: list[float] = []
    for _ in range(_WITNESS_SAMPLES):
        direct = Genome.new_fully_connected(
            cfg.genome, cfg.network.num_inputs, cfg.network.num_outputs, rng
        )
        witness_roughness.append(
            _circular_roughness(
                _ring_weights(direct, output_node, cfg.sensors.num_rays)
            )
        )

    print(
        f"geometric regularity (lower = smoother across adjacent rays): "
        f"CPPN substrate {cppn_roughness:.3f}  vs  {_WITNESS_SAMPLES} random direct "
        f"genomes {st.mean(witness_roughness):.3f} "
        f"(±{st.pstdev(witness_roughness):.3f})"
    )


def _report_resolution_transfer(
    cfg: SimConfig, cppn_genome: Genome, base_score: float
) -> None:
    hi_res_sensors = dataclasses.replace(cfg.sensors, num_rays=cfg.sensors.num_rays * 2)
    hi_res_substrate = build_substrate_network(
        cppn_genome, hi_res_sensors, cfg.network, cfg.hyperneat
    )
    hi_res_score = steer_score(hi_res_substrate, hi_res_sensors)
    print(
        f"resolution transfer (same CPPN, num_rays {cfg.sensors.num_rays} -> "
        f"{hi_res_sensors.num_rays}, NOT re-evolved): "
        f"steer_score {base_score:+.3f} -> {hi_res_score:+.3f}"
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
