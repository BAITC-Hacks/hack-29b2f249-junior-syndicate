"""Topology stress tests and ranking sensitivity with reproducible baselines."""
from __future__ import annotations

import random
from copy import deepcopy
import networkx as nx
import numpy as np
import pandas as pd

from .features import calculate_features
from .graph_builder import communities
from .load_data import InputData
from .scoring import assign_roles, assign_priority


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


def assess_ranking_stability(data: InputData, graph: nx.DiGraph, features: pd.DataFrame,
                             config: dict, top_n: int = 20) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not isinstance(top_n, int) or isinstance(top_n, bool) or top_n < 1:
        raise ValueError("top_n must be a positive integer")
    if features.empty or features.gid.duplicated().any() or set(features.gid) != set(data.nodes.gid):
        raise ValueError("Stability requires features for every input node exactly once")
    top_n = min(top_n, len(features))
    variants = [("baseline", "baseline", "none", 1.0, config)]
    for factor in config["priority"]:
        for multiplier in (.9, 1.1):
            changed = deepcopy(config)
            changed["priority"][factor] *= multiplier
            total = sum(changed["priority"].values())
            changed["priority"] = {name: weight / total for name, weight in changed["priority"].items()}
            variants.append((f"priority__{factor}__{multiplier}", "priority_weights", factor, multiplier, changed))
    for multiplier in (.8, 1.2):
        changed = deepcopy(config)
        changed["community_resolution"] *= multiplier
        variants.append((f"resolution__{multiplier}", "community_resolution", "community_resolution", multiplier, changed))
    base_roles = assign_roles(features, config)
    rows = []
    ranks = {"priority_weights": [], "community_resolution": []}
    role_changes = {kind: [] for kind in ranks}
    for scenario, kind, parameter, multiplier, changed in variants:
        if kind == "community_resolution":
            cluster_map = communities(graph, changed["random_seed"], changed["community_resolution"])
            current_features = calculate_features(data.nodes, data.edges, data.transactions, graph, cluster_map,
                                                  changed["betweenness_samples"], changed["betweenness_exact_limit"], changed["random_seed"])
            current_roles = assign_roles(current_features, changed)
        else:
            current_roles = base_roles
        scored = assign_priority(current_roles, changed)
        ranked = scored.sort_values(["priority_score", "gid"], ascending=[False, True]).set_index("gid")
        ranked["rank"] = np.arange(1, len(ranked) + 1)
        if kind == "baseline":
            baseline = ranked
            base_top = baseline.index[:top_n]
        current_top = ranked.index[:top_n]
        aligned = ranked.reindex(baseline.index)
        shifts = (aligned["rank"] - baseline["rank"]).abs()
        changes = aligned.role.ne(baseline.role)
        overlap = len(set(base_top) & set(current_top))
        cutoff = float(ranked.priority_score.iloc[top_n - 1])
        rows.append({
            "scenario": scenario, "kind": kind, "parameter": parameter, "multiplier": multiplier,
            "community_resolution": changed["community_resolution"],
            **{f"weight__{name}": weight for name, weight in changed["priority"].items()},
            "n_nodes": len(ranked), "top_n": top_n, "n_clusters": int(ranked.cluster_id.nunique()),
            "overlap_count": overlap, "overlap_fraction": overlap / top_n,
            "entered_gids": ", ".join(str(gid) for gid in current_top if gid not in base_top),
            "left_gids": ", ".join(str(gid) for gid in base_top if gid not in current_top),
            "mean_abs_rank_shift_base_top": float(shifts.loc[base_top].mean()),
            "max_abs_rank_shift_base_top": int(shifts.loc[base_top].max()),
            "role_changes": int(changes.sum()), "positive_score_nodes": int(ranked.priority_score.gt(0).sum()),
            "cutoff_score": cutoff, "cutoff_tied_nodes": int(ranked.priority_score.eq(cutoff).sum()),
            "cutoff_tie_crosses_top_n": bool(len(ranked) > top_n and ranked.priority_score.iloc[top_n] == cutoff),
        })
        if kind != "baseline":
            ranks[kind].append(aligned["rank"].rename(scenario))
            role_changes[kind].append(changes.rename(scenario))
    node_tables = []
    for kind, results in ranks.items():
        matrix = pd.concat(results, axis=1)
        changed_roles = pd.concat(role_changes[kind], axis=1)
        hits = matrix.le(top_n).sum(axis=1)
        node_tables.append(pd.DataFrame({
            "kind": kind, "baseline_rank": baseline["rank"], "baseline_role": baseline.role,
            "baseline_priority_score": baseline.priority_score,
            "in_baseline_top": baseline["rank"].le(top_n), "scenario_count": len(results),
            "top_n_hits": hits, "top_n_fraction": hits / len(results),
            "best_rank": matrix.min(axis=1), "worst_rank": matrix.max(axis=1),
            "max_abs_rank_shift": matrix.sub(baseline["rank"], axis=0).abs().max(axis=1),
            "role_change_count": changed_roles.sum(axis=1),
        }).reset_index())
    return pd.DataFrame(rows), pd.concat(node_tables, ignore_index=True)
