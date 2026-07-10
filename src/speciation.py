"""Genetic-distance metrics: diversity and species count (read-only observers).

Implements the NEAT compatibility distance (Stanley & Miikkulainen 2002,
equation 2 — the unnormalised form used by the canonical C++ implementation):

    delta = c_excess * E + c_disjoint * D + c_weight * W

where connection genes are aligned by innovation number, ``E``/``D`` are the
excess/disjoint gene counts and ``W`` is the mean absolute weight difference of
matching genes. Two genomes whose distance is below ``compatibility_threshold``
belong to the same species (greedy single-pass clustering, as in canonical
NEAT).

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

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from src.config import SpeciationConfig
from src.genome import Genome


@dataclass(frozen=True)
class _Profile:
    """A genome's connection genes indexed by innovation, computed once.

    Every field the O(pop²) callers below need per genome (:func:`assign_species`,
    :func:`mean_pairwise_distance`) but that :func:`compatibility_distance`
    otherwise recomputes from scratch on every pairwise call it's part of —
    ``weights``/``innovations``/``max_innovation`` each cost O(connections) to
    build, and rebuilding them once per *pair* rather than once per *genome*
    was the dominant cost of both functions (profiled ~300ms at pop≈230, enough
    to visibly stall the render loop every ``logging.log_interval_ticks``).
    """

    weights: dict[int, float]
    innovations: frozenset[int]
    max_innovation: int  # -1 for a genome with no connections


def _profile(genome: Genome) -> _Profile:
    weights = {c.innovation: c.weight for c in genome.connections}
    innovations = frozenset(weights)
    return _Profile(weights, innovations, max(innovations, default=-1))


def _distance(a: _Profile, b: _Profile, config: SpeciationConfig) -> float:
    """Core NEAT compatibility distance between two precomputed profiles."""
    if not a.weights and not b.weights:
        return 0.0

    matching = a.innovations & b.innovations

    # Genes beyond the smaller genome's innovation horizon are excess, not disjoint.
    boundary = min(a.max_innovation, b.max_innovation)
    excess = 0
    disjoint = 0
    for innovation in a.innovations ^ b.innovations:
        if innovation > boundary:
            excess += 1
        else:
            disjoint += 1

    if matching:
        weight_diff = sum(abs(a.weights[i] - b.weights[i]) for i in matching) / len(
            matching
        )
    else:
        weight_diff = 0.0

    return (
        config.c_excess * excess
        + config.c_disjoint * disjoint
        + config.c_weight * weight_diff
    )


def compatibility_distance(
    first: Genome, second: Genome, config: SpeciationConfig
) -> float:
    """NEAT compatibility distance between two genomes (0.0 when identical).

    Connection genes are aligned by innovation number. A gene present in only one
    genome counts as *excess* when its innovation exceeds the other genome's
    largest innovation, otherwise *disjoint*. The weight term is the mean
    absolute difference over genes shared by both.

    One-off convenience wrapper (mate selection, tests). Callers comparing many
    genomes against each other (:func:`assign_species`, :func:`mean_pairwise_distance`)
    build a :class:`_Profile` per genome ONCE instead of using this function
    pairwise — see their docstrings.
    """
    return _distance(_profile(first), _profile(second), config)


def assign_species(genomes: Sequence[Genome], config: SpeciationConfig) -> list[int]:
    """Species id (0-based) for each genome, via greedy single-pass clustering.

    Each genome joins the first representative within ``compatibility_threshold``
    (in ``genomes`` order); a genome matching none becomes a new representative
    and its own species. Same clustering rule as canonical NEAT — deterministic
    given a fixed input order, which the caller controls.
    """
    profiles = [_profile(g) for g in genomes]
    rep_profiles: list[_Profile] = []
    assignments: list[int] = []
    for profile in profiles:
        species_id = next(
            (
                i
                for i, rep in enumerate(rep_profiles)
                if _distance(profile, rep, config) < config.compatibility_threshold
            ),
            None,
        )
        if species_id is None:
            rep_profiles.append(profile)
            species_id = len(rep_profiles) - 1
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
    unlike :func:`assign_species` (fast — few species, each genome compared
    against a handful of representatives), this one is inherently O(pop²)
    pairs, and even with the per-genome ``_Profile`` cache the remaining
    Python-level set/loop work per pair stalled the render loop every
    ``logging.log_interval_ticks`` (~150ms at pop≈230, worse near
    ``population.max_size``). The number of *distinct* innovations across a
    population stays small in practice (~100-200: most genomes share the
    founder's connections, only a few survive structural mutation), so a
    dense ``(pop, innovations)`` matrix is cheap; each genome's row of
    distances to the rest is then one vectorised NumPy comparison instead of
    ``pop`` individual Python-level ones. Numerically equivalent to the
    ``_distance`` scalar path (same formula), not necessarily bit-identical
    (different float summation order).
    """
    count = len(genomes)
    if count < 2:
        return 0.0

    innovations = sorted({c.innovation for g in genomes for c in g.connections})
    if not innovations:
        return 0.0  # every genome is connection-less -> distance 0.0 for every pair
    index = {innovation: col for col, innovation in enumerate(innovations)}
    innov_values = np.array(innovations, dtype=np.int64)

    num_cols = len(innovations)
    weights = np.zeros((count, num_cols), dtype=np.float64)
    present = np.zeros((count, num_cols), dtype=bool)
    max_innovation = np.full(count, -1, dtype=np.int64)
    for row, genome in enumerate(genomes):
        if not genome.connections:
            continue
        cols = [index[c.innovation] for c in genome.connections]
        weights[row, cols] = [c.weight for c in genome.connections]
        present[row, cols] = True
        max_innovation[row] = max(c.innovation for c in genome.connections)

    total = 0.0
    for i in range(count - 1):
        rest = slice(i + 1, count)
        xor = present[i] ^ present[rest]  # (R, K): gene present in exactly one
        boundary = np.minimum(max_innovation[i], max_innovation[rest])  # (R,)
        excess = (xor & (innov_values > boundary[:, None])).sum(axis=1)
        disjoint = xor.sum(axis=1) - excess

        matching = present[i] & present[rest]  # (R, K)
        match_count = matching.sum(axis=1)
        weight_sum = (np.abs(weights[i] - weights[rest]) * matching).sum(axis=1)
        weight_diff = np.divide(
            weight_sum,
            match_count,
            out=np.zeros_like(weight_sum),
            where=match_count > 0,
        )

        row_distance = (
            config.c_excess * excess
            + config.c_disjoint * disjoint
            + config.c_weight * weight_diff
        )
        total += float(row_distance.sum())

    pairs = count * (count - 1) // 2
    return total / pairs
