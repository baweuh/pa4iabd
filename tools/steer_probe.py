"""Behavioural probe: does a genome steer TOWARD apples?

Reusable across lever experiments. Reconstructs the network from a best-genome
JSON and measures the Pearson correlation between "apple is on the left" and
"turns left" (a lone apple placed on each egocentric ray). Score 1.0 = perfect
forager, 0.0 = ignores apples, negative = anti-forager. Compares the champion
against a pool of random newborns as a null baseline.

Usage: python -m tools.steer_probe <best_genome.json> [config.yaml]
"""

from __future__ import annotations

import math
import statistics as st
import sys
from random import Random

from src.config import SensorConfig, SimConfig
from src.genome import TRACKER, Genome
from src.network import NeuralNetwork


def _probe_inputs(k: int, sensors: SensorConfig) -> list[float]:
    """Build a sensor vector with a lone apple on ray k, matching the configured
    sensor layout (mirrors ``Agent.sense()``'s toggle logic exactly)."""
    num_rays = sensors.num_rays
    apple_dist = [1.0] * num_rays
    apple_dist[k] = 0.2
    wall_dist = [1.0] * num_rays  # walls never closer than the probed apple
    appf = [0.0] * num_rays
    appf[k] = 1.0
    wallf = [0.0] * num_rays
    if sensors.split_distance:
        vec = apple_dist + wall_dist + appf + wallf
    else:
        combined = [min(a, w) for a, w in zip(apple_dist, wall_dist)]
        vec = combined + appf + wallf
    vec = vec + [0.5]  # energy
    if sensors.proprioception:
        vec.append(0.0)  # actual_speed = still
    if sensors.apples_in_view:
        vec.append(1.0 / num_rays)  # exactly one ray sees an apple
    if len(vec) != sensors.num_inputs:
        raise ValueError(
            f"probe built {len(vec)} inputs, expected {sensors.num_inputs}"
        )
    return vec


def steer_score(net: NeuralNetwork, sensors: SensorConfig) -> float:
    """Pearson r between 'apple on the left' and 'turns left'."""
    num_rays = sensors.num_rays
    xs: list[float] = []
    ys: list[float] = []
    for k in range(1, num_rays):
        if k == num_rays // 2:
            continue  # directly behind: ambiguous
        ang = k * (2 * math.pi / num_rays)
        raw = net.activate(_probe_inputs(k, sensors))
        xs.append(math.sin(ang))
        ys.append(math.tanh(raw[1]))
    mx, my = st.mean(xs), st.mean(ys)
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    dy = math.sqrt(sum((b - my) ** 2 for b in ys))
    return num / (dx * dy) if dx * dy > 1e-12 else 0.0


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
