"""Behavioural novelty for additive reproduction bonuses (novelty search).

Lehman & Stanley 2011. A network's behaviour is characterised by its *steering
response profile*: the turn output it produces to a lone apple placed on each
ray. This depends only on the network, which is fixed for an agent's whole life
(weights frozen, topology sorted once), so the descriptor is deterministic and
computed once per agent (cached on the Agent, like the network itself).

Novelty is the mean distance to the ``neighbors`` nearest behaviours in the
current population. In ``src.simulation`` it is ADDED to raw fitness in the
reproduction priority — never replacing it. Additive is the only pattern that
has held up on this project (the reducer mechanisms were all falsified); a novel
agent gets a *bonus* chance to reproduce, it is never penalised.

The probe vector mirrors ``Agent.sense()``'s layout toggles exactly (same
construction as ``tools.steer_probe``), so the descriptor is valid for every
sensor configuration (49 or 67 inputs).
"""

from __future__ import annotations

import math

import numpy as np

from src.config import SensorConfig
from src.network import NeuralNetwork


def probe_apple_on_ray(k: int, sensors: SensorConfig) -> list[float]:
    """Sensor vector with a single apple on ray ``k`` (layout-aware).

    Shared with ``src.diagnostics.steer_score`` — same synthetic-input
    construction, two different consumers (novelty descriptor vs. the
    steering-correlation probe migrated from ``tools/steer_probe.py``).
    """
    num_rays = sensors.num_rays
    apple_dist = [1.0] * num_rays
    apple_dist[k] = 0.2  # a close apple on ray k
    wall_dist = [1.0] * num_rays  # walls never nearer than the probed apple
    apple_flag = [0.0] * num_rays
    apple_flag[k] = 1.0
    wall_flag = [0.0] * num_rays
    if sensors.split_distance:
        vec = apple_dist + wall_dist + apple_flag + wall_flag
    else:
        combined = [min(a, w) for a, w in zip(apple_dist, wall_dist)]
        vec = combined + apple_flag + wall_flag
    vec = vec + [0.5]  # energy at mid-range
    if sensors.proprioception:
        vec.append(0.0)  # actual_speed: still
    if sensors.apples_in_view:
        vec.append(1.0 / num_rays)  # exactly one ray sees an apple
    return vec


def behavior_descriptor(net: NeuralNetwork, sensors: SensorConfig) -> list[float]:
    """Turn-response profile: ``tanh(turn output)`` to an apple on each ray.

    Length ``num_rays``. Two networks that steer differently toward apples get
    distant descriptors; two that steer the same get close ones — exactly the
    behaviour space novelty should reward diversity in.
    """
    return [
        math.tanh(net.activate(probe_apple_on_ray(k, sensors))[1])
        for k in range(sensors.num_rays)
    ]


def population_novelty(
    descriptors: np.ndarray, neighbors: int, archive: np.ndarray | None = None
) -> np.ndarray:
    """Mean distance to the ``neighbors`` nearest behaviours, per agent.

    ``descriptors`` is ``(P, D)``; returns ``(P,)``. Self is excluded. With fewer
    than ``neighbors`` others, averages over all of them. 0/1-agent populations
    have novelty 0 everywhere (unless ``archive`` gives them something to be
    novel against).

    ``archive`` (``(A, D)``, optional) is a pool of past behaviours — from
    extinct lineages or earlier generations — that widens the neighbourhood
    without being scored itself (Lehman & Stanley 2011). Novelty is measured
    against ``descriptors ∪ archive``; the archive only adds candidates to be
    novel against, it never displaces the current population.
    """
    count = descriptors.shape[0]
    has_archive = archive is not None and archive.shape[0] > 0
    if count <= 1 and not has_archive:
        return np.zeros(count)
    pool = (
        np.concatenate([descriptors, archive], axis=0) if has_archive else descriptors
    )
    diff = descriptors[:, None, :] - pool[None, :, :]  # (P, P+A, D)
    dist = np.sqrt(np.sum(diff * diff, axis=2))  # (P, P+A)
    self_idx = np.arange(count)
    dist[self_idx, self_idx] = np.inf  # never count the agent against itself
    k = min(neighbors, pool.shape[0] - 1)
    nearest = np.partition(dist, k - 1, axis=1)[:, :k]  # k smallest per row
    return nearest.mean(axis=1)
