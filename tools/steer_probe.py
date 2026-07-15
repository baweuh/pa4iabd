"""Behavioural probe: does a genome steer TOWARD apples?

Reusable across lever experiments. Reconstructs the network from a best-genome
JSON and measures the Pearson correlation between "apple is on the left" and
"turns left" (a lone apple placed on each egocentric ray). Score 1.0 = perfect
forager, 0.0 = ignores apples, negative = anti-forager. Compares the champion
against a pool of random newborns as a null baseline.

Usage: python -m tools.steer_probe <best_genome.json> [config.yaml]
"""

from __future__ import annotations

import statistics as st
import sys
from random import Random

from src.config import SimConfig
from src.diagnostics import steer_score  # noqa: F401  (re-exported for callers)
from src.genome import TRACKER, Genome
from src.network import NeuralNetwork


def main(argv: list[str]) -> int:
    genome_path = argv[1]
    config_path = argv[2] if len(argv) > 2 else "config/default.yaml"
    cfg = SimConfig.from_yaml(config_path)

    champ = Genome.from_json(open(genome_path, encoding="utf-8").read())
    hidden = sum(1 for n in champ.nodes if n.node_type == "hidden")
    enabled = sum(1 for c in champ.connections if c.enabled)
    weights = [c.weight for c in champ.connections if c.enabled]
    cs = steer_score(NeuralNetwork(champ, cfg.network), cfg.sensors)

    rng = Random(1234)
    rand_scores: list[float] = []
    for _ in range(200):
        TRACKER.reset()
        g = Genome.new_fully_connected(
            cfg.genome, cfg.network.num_inputs, cfg.network.num_outputs, rng
        )
        rand_scores.append(steer_score(NeuralNetwork(g, cfg.network), cfg.sensors))

    better = sum(1 for r in rand_scores if r > cs)
    print(
        f"champion topology : {hidden} hidden, {enabled} enabled conns, "
        f"weight std {st.pstdev(weights):.3f}"
    )
    print(f"champion steer r  : {cs:+.3f}")
    print(
        f"random baseline   : mean {st.mean(rand_scores):+.3f}  "
        f"range [{min(rand_scores):+.3f}, {max(rand_scores):+.3f}]"
    )
    print(
        f"random better than champion : {better}/200  "
        f"(champion percentile {100 * (200 - better) / 200:.0f}%)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
