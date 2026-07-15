"""Trace the final champion's real ancestry, one probe per generation.

2nd tool agreed with Robin for the HyperNEAT chantier (research-roadmap
item #4), needed before the falsification campaign: "observe only the last
generation / follow one lineage" WITHOUT shrinking the population (a smaller
population reopens founder drift, cf. the falsified island model — see
docs/FALSIFIED-islands.md). Drives a REAL, full-population run (genuine
selection, nothing artificial) and reconstructs the champion's actual
parent chain back to a founder — not a proxy like ``best_agents/``'s
coarse timeline of successive record-holders (a later record-setter is
*usually* a descendant of the earlier one under selection, but not
provably so).

Ancestry bookkeeping (monkeypatches ``Agent.reproduce`` for the lifetime of
this process only, never touches src/ — same technique as
``tools/apple_capture_probe.py``): every birth gets a small sequential
integer id and records ``(parent_id, tick, genome)`` — the genome only
(~10-100 small dataclass objects), never the full ``Agent`` (network,
position history, environment ref). This is a deliberate, BOUNDED,
single-run cost (a few thousand small genomes for a full campaign-length
run) — nothing like the ``_birth_events`` leak fixed earlier this project
(which pinned full ``Agent`` objects, unboundedly, in every production
run). Diagnostics (steer_score/descriptor/structure) are computed only for
the handful of ancestors actually on the final chain, at the very end, not
for every birth.

Usage: python -m tools.trace_lineage <config.yaml> <ticks> [seed]
"""

# pylint: disable=protected-access
# _lineage_id is a dynamic attribute this tool adds to Agent instances for
# its own bookkeeping (never touches src/), not a real internal of the class.

from __future__ import annotations

import itertools
import statistics as st
import sys
from random import Random

from src.agent import Agent
from src.config import SimConfig
from src.diagnostics import steer_score
from src.genome import Genome
from src.hyperneat import build_substrate_network
from src.network import NeuralNetwork
from src.novelty import behavior_descriptor
from src.simulation import Simulation


def main(argv: list[str]) -> int:
    config_path = argv[1]
    ticks = int(argv[2])
    cfg = SimConfig.from_yaml(config_path)
    seed = int(argv[3]) if len(argv) > 3 else cfg.simulation.seed

    lineage: dict[int, dict] = {}
    ids = itertools.count()
    sim = Simulation(cfg, Random(seed))
    original_reproduce = Agent.reproduce

    def reproduce_probe(self: Agent, mate: Agent | None = None) -> Agent:
        if not hasattr(self, "_lineage_id"):
            # Lazily tag: only true founders reach here (every child is
            # tagged at birth below), always born at tick 0.
            self._lineage_id = next(ids)  # type: ignore[attr-defined]
            lineage[self._lineage_id] = {
                "parent": None,
                "tick": 0,
                "genome": self.genome,
            }
        child = original_reproduce(self, mate)
        child._lineage_id = next(ids)  # type: ignore[attr-defined]
        lineage[child._lineage_id] = {
            "parent": self._lineage_id,
            "tick": sim.tick_count,
            "genome": child.genome,
        }
        return child

    Agent.reproduce = reproduce_probe  # type: ignore[method-assign]
    try:
        while not sim.is_extinct and sim.tick_count < ticks:
            sim.tick()
    finally:
        Agent.reproduce = original_reproduce  # type: ignore[method-assign]

    if sim.is_extinct or not sim.population:
        print(f"EXTINCT at tick {sim.tick_count}")
        return 0

    # steer_score (evolved steering competence), not apples_eaten: lifetime
    # apples conflates competence with longevity — a long-lived founder can
    # out-eat a genuinely better-evolved but younger descendant, which would
    # trivially pick a shallow (often single-node) lineage. Same convention
    # as run_and_probe.py/inspect_network.py.
    champion = max(sim.population, key=lambda a: a.steer_score)
    if not hasattr(champion, "_lineage_id"):
        # Alive but never reproduced: a founder, single-node lineage.
        champion._lineage_id = next(ids)  # type: ignore[attr-defined]
        lineage[champion._lineage_id] = {
            "parent": None,
            "tick": 0,
            "genome": champion.genome,
        }

    champion_id: int = champion._lineage_id  # type: ignore[attr-defined]
    chain = _walk_to_founder(lineage, champion_id)
    print(
        f"champion: tick {sim.tick_count}  apples_eaten {champion.apples_eaten}  "
        f"generation {champion.generation}  lineage depth {len(chain)}"
    )
    for entry in chain:
        _print_generation(cfg, entry)
    return 0


def _walk_to_founder(lineage: dict[int, dict], leaf_id: int) -> list[dict]:
    """Root-to-leaf ancestry chain (founder first, champion last)."""
    chain: list[dict] = []
    node_id: int | None = leaf_id
    while node_id is not None:
        entry = lineage[node_id]
        chain.append(entry)
        node_id = entry["parent"]
    chain.reverse()
    return chain


def _print_generation(cfg: SimConfig, entry: dict) -> None:
    genome: Genome = entry["genome"]
    net = (
        build_substrate_network(genome, cfg.sensors, cfg.network, cfg.hyperneat)
        if cfg.hyperneat.enabled
        else NeuralNetwork(genome, cfg.network)
    )
    score = steer_score(net, cfg.sensors)
    descriptor = behavior_descriptor(net, cfg.sensors)
    hidden = sum(1 for n in genome.nodes if n.node_type == "hidden")
    print(
        f"  tick {entry['tick']:>6}  genome {len(genome.nodes)}n/"
        f"{len(genome.connections)}c ({hidden} hidden)  "
        f"steer_score {score:+.3f}  mean|descriptor| "
        f"{st.mean(abs(v) for v in descriptor):.3f}"
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
