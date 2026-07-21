"""Run a config and report the INNATE vs LEARNED steering score, paired per agent.

The measurement the Hebbian chantier turns on, and the one ``run_and_probe``
cannot make: under ``hebbian.enabled`` the compiled network drifts away from the
genome during the agent's life (``NeuralNetwork.apply_hebbian``), so there are
two different steer scores for the same agent and they answer two different
questions.

    LEARNED  steer_score(agent.network)      — the plastic weights, here and now
    INNATE   steer_score(NeuralNetwork(agent.genome, ...))  — what it was born with

Learning is non-Lamarckian, so the genome still holds the innate wiring and the
innate network can always be rebuilt from it. Rebuilding it WITHOUT a
HebbianConfig also guarantees the probe cannot itself perturb anything.

  learned - innate  : does an individual's learning help ITS OWN foraging?
                      (Hebbian V1 failure mode n°1 — it was systematically
                      negative: agents learned against their own foraging.)
  innate vs control : does carrying plasticity handicap EVOLUTION itself?
                      (failure mode n°2 — the innate score collapsed well below
                      a no-plasticity control, the inverse of a Baldwin effect.)

Mode n°1 is a PAIRED comparison inside one run, which is why it is reported as a
mean of per-agent deltas and a win rate rather than a difference of two means.
Mode n°2 needs a separate control run (``config/default.yaml``, same seed) —
this tool only reports the innate half; compare across invocations.

Both scores are noisy from one snapshot to the next (the control alone swings
0.12-0.36 over a single run, see docs/DIAGNOSTIC-hebbian-v2.md), hence
``interval``: report at several checkpoints rather than trusting one endpoint.

Usage: python -m tools.hebbian_probe <config.yaml> <ticks> [label] [seed] [interval]

``interval`` defaults to ``ticks`` (a single report at the end).
"""

from __future__ import annotations

import statistics as st
import sys
from random import Random

from src.agent import Agent
from src.config import SimConfig
from src.diagnostics import steer_score
from src.network import NeuralNetwork
from src.simulation import Simulation


def innate_score(agent: Agent, cfg: SimConfig) -> float:
    """Steering score of the network the agent was BORN with.

    Rebuilt from the genome with no HebbianConfig: plasticity never writes back
    to the genome, so this is the inherited policy, stripped of whatever the
    agent learned. Passing no config also makes the rebuilt network inert — it
    records no activations and cannot learn from being measured.
    """
    return steer_score(NeuralNetwork(agent.genome, cfg.network), cfg.sensors)


def report(sim: Simulation, cfg: SimConfig, label: str) -> None:
    """Print one paired innate/learned snapshot of the living population.

    Flushed explicitly: a matrix of these runs is normally launched in parallel
    with stdout redirected to files, where Python block-buffers and no
    checkpoint would be readable until the process exits — which defeats the
    point of reporting at checkpoints on a run that takes minutes.
    """
    pop = sim.population
    if not pop:
        print(f"[{label}] tick {sim.tick_count}  POPULATION EMPTY", flush=True)
        return

    # Learned first: under plasticity Agent.steer_score bypasses its cache and
    # scores the current weights (see Agent.steer_score).
    learned = [a.steer_score for a in pop]
    innate = [innate_score(a, cfg) for a in pop]
    deltas = [lrn - inn for lrn, inn in zip(learned, innate)]
    threshold = cfg.diagnostics.forager_threshold
    foragers = sum(1 for s in learned if s > threshold)

    print(
        f"[{label}] tick {sim.tick_count}  pop {len(pop)}  "
        f"record {sim.record_apples}  repro {sim.total_reproductions}"
    )
    print(f"  innate  : mean {st.mean(innate):+.3f}  median {st.median(innate):+.3f}")
    print(f"  learned : mean {st.mean(learned):+.3f}  median {st.median(learned):+.3f}")
    print(
        f"  delta (learned-innate) : mean {st.mean(deltas):+.4f}  "
        f"median {st.median(deltas):+.4f}  "
        f"improved {sum(1 for d in deltas if d > 0)}/{len(deltas)}"
    )

    # Whole-population deltas understate learning badly. The update is
    # dw = lr * (m - m_bar) * e, so an agent that has never eaten has m = m_bar = 0
    # and its weights never move AT ALL — its delta is exactly zero, not a small
    # one. With ~3 apples per life median (docs/DIAGNOSTIC-hebbian-v1.md) most of
    # the living population is in that state at any moment, so averaging over
    # everyone mostly averages zeros. Splitting on "did this agent's brain
    # actually change" is threshold-free and asks the real question: among agents
    # that DID learn, did learning help them?
    learners = [d for d in deltas if d != 0.0]
    if learners:
        print(
            f"  delta, agents whose weights actually moved : "
            f"mean {st.mean(learners):+.4f}  median {st.median(learners):+.4f}  "
            f"improved {sum(1 for d in learners if d > 0)}/{len(learners)} "
            f"({100 * len(learners) / len(pop):.0f}% of pop)"
        )
    else:
        print("  delta, agents whose weights actually moved : none")

    print(
        f"  foragers (learned r>{threshold}) : {100 * foragers / len(pop):.0f}%",
        flush=True,
    )


def main(argv: list[str]) -> int:
    config_path = argv[1]
    ticks = int(argv[2])
    label = argv[3] if len(argv) > 3 else config_path
    cfg = SimConfig.from_yaml(config_path)
    seed = int(argv[4]) if len(argv) > 4 else cfg.simulation.seed
    interval = int(argv[5]) if len(argv) > 5 else ticks

    sim = Simulation(cfg, Random(seed))
    while not sim.is_extinct and sim.tick_count < ticks:
        sim.tick()
        if sim.tick_count % interval == 0:
            report(sim, cfg, label)

    if sim.is_extinct:
        print(f"[{label}] EXTINCT at tick {sim.tick_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
