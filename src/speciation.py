"""Genetic-distance metrics: diversity and species count (read-only observers).

poc3: with a fixed topology, every genome shares the exact same weight-vector
layout — there is no more excess/disjoint gene concept (that only made sense
when genomes could carry different connection sets, aligned by NEAT
innovation number). Distance collapses to a plain mean absolute weight
difference over the shared vector:

    delta = c_weight * mean(|w1 - w2|)

Two genomes whose distance is below ``compatibility_threshold`` belong to the
same species (greedy single-pass clustering, as in canonical NEAT).

``compatibility_distance``/``count_species``/``mean_pairwise_distance`` are
read-only observers (metrics CSV, mate selection). ``assign_species`` backs
those AND fitness sharing in ``Simulation`` (species-relative reproduction
priority — a large species no longer autowins scarce reproduction slots just
by raw fitness, protecting small/novel species from being crushed before they
can prove themselves; canonical NEAT, Stanley & Miikkulainen 2002).

Invariants honoured here:
- n°1 — zero hardcoding: every coefficient comes from :class:`SpeciationConfig`.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

from src.config import SpeciationConfig
from src.genome import Genome


def compatibility_distance(
    first: Genome, second: Genome, config: SpeciationConfig
) -> float:
    """Genetic distance between two genomes (0.0 when identical).

    Both genomes share the same fixed weight-vector layout by construction,
    so alignment is trivial — a plain elementwise mean absolute difference,
    scaled by ``c_weight``.
    """
    if first.weights.size == 0:
        return 0.0
    return config.c_weight * float(np.mean(np.abs(first.weights - second.weights)))


def assign_species(genomes: Sequence[Genome], config: SpeciationConfig) -> list[int]:
    """Species id (0-based) for each genome, via greedy single-pass clustering.

    Each genome joins the first representative within ``compatibility_threshold``
    (in ``genomes`` order); a genome matching none becomes a new representative
    and its own species. Same clustering rule as canonical NEAT — deterministic
    given a fixed input order, which the caller controls.
    """
    representatives: list[Genome] = []
    assignments: list[int] = []
    for genome in genomes:
        species_id = next(
            (
                i
                for i, rep in enumerate(representatives)
                if compatibility_distance(genome, rep, config)
                < config.compatibility_threshold
            ),
            None,
        )
        if species_id is None:
            representatives.append(genome)
            species_id = len(representatives) - 1
        assignments.append(species_id)
    return assignments


def count_species(genomes: Sequence[Genome], config: SpeciationConfig) -> int:
    """Number of species via greedy clustering on compatibility distance."""
    return len(set(assign_species(genomes, config)))


def mean_pairwise_distance(
    genomes: Sequence[Genome], config: SpeciationConfig
) -> float:
    """Mean compatibility distance over all unordered genome pairs (0.0 if < 2).

    A scalar summary of population-wide genetic diversity: it falls toward 0 as
    the population converges onto a single lineage and rises as lineages diverge.

    NumPy-vectorised (same "freeze then perceive" idea as ``batch_sense``):
    stacks every genome's weight vector into one ``(pop, num_weights)`` matrix
    (all genomes share the same shape by construction) and computes every
    pairwise mean-absolute-difference at once, instead of ``pop`` individual
    Python-level calls to :func:`compatibility_distance`.
    """
    count = len(genomes)
    if count < 2:
        return 0.0

    weights = np.stack([g.weights for g in genomes], axis=0)  # (pop, num_weights)
    if weights.shape[1] == 0:
        return 0.0

    total = 0.0
    for i in range(count - 1):
        diffs = np.abs(weights[i] - weights[i + 1 :])  # (R, num_weights)
        total += float(diffs.mean(axis=1).sum())

    pairs = count * (count - 1) // 2
    return config.c_weight * total / pairs
