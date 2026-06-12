"""Genetic-distance metrics: diversity and species count (read-only observers).

Implements the NEAT compatibility distance (Stanley & Miikkulainen 2002,
equation 2 — the unnormalised form used by the canonical C++ implementation):

    delta = c_excess * E + c_disjoint * D + c_weight * W

where connection genes are aligned by innovation number, ``E``/``D`` are the
excess/disjoint gene counts and ``W`` is the mean absolute weight difference of
matching genes. Two genomes whose distance is below ``compatibility_threshold``
belong to the same species (greedy single-pass clustering, as in canonical
NEAT).

These functions never influence selection or reproduction — the simulation stays
a continuous, asexual ALife model. They exist so evolution becomes *measurable*:
genetic-diversity collapse and the appearance of distinct species show up in the
metrics CSV (CLAUDE.md goal: "voir des espèces apparaître").

Invariants honoured here:
- n°1 — zero hardcoding: every coefficient comes from :class:`SpeciationConfig`.
"""

from __future__ import annotations

from typing import Sequence

from src.config import SpeciationConfig
from src.genome import Genome


def compatibility_distance(
    first: Genome, second: Genome, config: SpeciationConfig
) -> float:
    """NEAT compatibility distance between two genomes (0.0 when identical).

    Connection genes are aligned by innovation number. A gene present in only one
    genome counts as *excess* when its innovation exceeds the other genome's
    largest innovation, otherwise *disjoint*. The weight term is the mean
    absolute difference over genes shared by both.
    """
    weights_a = {c.innovation: c.weight for c in first.connections}
    weights_b = {c.innovation: c.weight for c in second.connections}
    if not weights_a and not weights_b:
        return 0.0

    innov_a = set(weights_a)
    innov_b = set(weights_b)
    matching = innov_a & innov_b

    # Genes beyond the smaller genome's innovation horizon are excess, not disjoint.
    boundary = min(
        max(weights_a) if weights_a else -1,
        max(weights_b) if weights_b else -1,
    )
    excess = 0
    disjoint = 0
    for innovation in innov_a ^ innov_b:
        if innovation > boundary:
            excess += 1
        else:
            disjoint += 1

    if matching:
        weight_diff = sum(abs(weights_a[i] - weights_b[i]) for i in matching) / len(
            matching
        )
    else:
        weight_diff = 0.0

    return (
        config.c_excess * excess
        + config.c_disjoint * disjoint
        + config.c_weight * weight_diff
    )


def count_species(genomes: Sequence[Genome], config: SpeciationConfig) -> int:
    """Number of species via greedy clustering on compatibility distance.

    Each genome joins the first representative within ``compatibility_threshold``;
    a genome matching none becomes a new representative. Returns the
    representative count (0 for an empty population).
    """
    representatives: list[Genome] = []
    for genome in genomes:
        if not any(
            compatibility_distance(genome, rep, config) < config.compatibility_threshold
            for rep in representatives
        ):
            representatives.append(genome)
    return len(representatives)


def mean_pairwise_distance(
    genomes: Sequence[Genome], config: SpeciationConfig
) -> float:
    """Mean compatibility distance over all unordered genome pairs (0.0 if < 2).

    A scalar summary of population-wide genetic diversity: it falls toward 0 as
    the population converges onto a single lineage and rises as lineages diverge.
    """
    count = len(genomes)
    if count < 2:
        return 0.0
    total = 0.0
    pairs = 0
    for i in range(count):
        for j in range(i + 1, count):
            total += compatibility_distance(genomes[i], genomes[j], config)
            pairs += 1
    return total / pairs
