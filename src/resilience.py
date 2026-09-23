"""Counterfactual topology stress test with a reproducible random baseline."""
from __future__ import annotations

import random
import networkx as nx
import numpy as np
import pandas as pd


def assess_resilience(graph: nx.DiGraph, ranked_gids: list[int], seed: int = 42,
                      repetitions: int = 30, removal_counts: tuple[int, ...] = (1, 3, 5, 10, 20)) -> pd.DataFrame:
    undirected = graph.to_undirected()
    node_ids = sorted(undirected)
    baseline = nx.number_connected_components(undirected)
    rng = random.Random(seed)
    rows = []
    for count in removal_counts:
        if count >= len(node_ids):
            continue
        for strategy in ("top_priority", "random"):
            trials = []
            for _ in range(1 if strategy == "top_priority" else repetitions):
                removed = set(ranked_gids[:count] if strategy == "top_priority" else rng.sample(node_ids, count))
                remaining = undirected.subgraph([gid for gid in node_ids if gid not in removed])
                sizes = [len(component) for component in nx.connected_components(remaining)]
                trials.append((len(sizes), max(sizes, default=0)))
            values = np.asarray(trials, dtype=float)
            rows.append({"removed_n": count, "strategy": strategy, "trials": len(trials),
                         "components_mean": float(values[:, 0].mean()),
                         "fragmentation_increase": float(values[:, 0].mean() - baseline),
                         "largest_component_mean": float(values[:, 1].mean()),
                         "largest_component_std": float(values[:, 1].std()),
                         "largest_component_remaining_fraction": float(values[:, 1].mean() / (len(node_ids) - count))})
    return pd.DataFrame(rows, columns=["removed_n", "strategy", "trials", "components_mean", "fragmentation_increase", "largest_component_mean", "largest_component_std", "largest_component_remaining_fraction"])
