"""Observed financial, structural and capacity-limited temporal metrics."""
from __future__ import annotations

from collections import Counter, deque
import numpy as np
import networkx as nx
import pandas as pd


def percentile_score(series: pd.Series) -> pd.Series:
    values = series.fillna(0).clip(lower=0)
    result = pd.Series(0.0, index=series.index)
    positive = values > 0
    result.loc[positive] = values.loc[positive].rank(pct=True, method="average")
    return result


def safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return numerator.divide(denominator.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)


def temporal_features(nodes: pd.DataFrame, transactions: pd.DataFrame) -> pd.DataFrame:
    incoming = {gid: group for gid, group in transactions.groupby("dst")}
    outgoing = {gid: group for gid, group in transactions.groupby("src")}
    empty = transactions.iloc[:0]
    records = []
    for gid in nodes.gid:
        received, sent = incoming.get(gid, empty), outgoing.get(gid, empty)
        related = pd.concat([received, sent[sent.dst.ne(gid)]]).sort_values("date")
        gaps = related.date.diff().dt.total_seconds().div(3600).dropna()
        received = received[received.src.ne(gid)]
        sent = sent[sent.dst.ne(gid)]
        events = [(row.date, 1, float(row.sum_kzt)) for row in received.itertuples()]
        events.extend((row.date, 0, float(row.sum_kzt)) for row in sent.itertuples())
        events.sort()
        ratios = {}
        for hours in (24, 48):
            credits: deque = deque()
            matched = 0.0
            for moment, direction, amount in events:
                while credits and (moment - credits[0][0]).total_seconds() > hours * 3600:
                    credits.popleft()
                if direction == 1:
                    credits.append([moment, amount])
                else:
                    while credits and amount > 0:
                        used = min(amount, credits[0][1])
                        amount -= used
                        credits[0][1] -= used
                        matched += used
                        if credits[0][1] <= 1e-8:
                            credits.popleft()
            ratios[hours] = matched / received.sum_kzt.sum() if not received.empty else 0.0
        records.append({
            "gid": gid, "active_days": related.date.dt.date.nunique(),
            "first_tx_date": related.date.min(), "last_tx_date": related.date.max(),
            "avg_gap_hours": gaps.mean(), "median_gap_hours": gaps.median(),
            "forwarded_within_24h_ratio": ratios[24], "forwarded_within_48h_ratio": ratios[48],
        })
    return pd.DataFrame(records)


def calculate_features(nodes: pd.DataFrame, edges: pd.DataFrame, transactions: pd.DataFrame,
                       graph: nx.DiGraph, cluster_map: dict[int, int],
                       betweenness_samples: int = 256, exact_limit: int = 1000, random_seed: int = 42) -> pd.DataFrame:
    frame = nodes.set_index("gid").copy()
    for side, endpoint in (("in", "dst"), ("out", "src")):
        stats = transactions.groupby(endpoint).sum_kzt.agg(["sum", "size", "mean", "median", "max"])
        stats.columns = [f"sum_{side}", f"n_{side}_tx", f"avg_{side}_tx", f"median_{side}_tx", f"max_{side}_tx"]
        frame = frame.join(stats)
    frame = frame.fillna(0)
    topology = graph.copy()
    topology.remove_edges_from(nx.selfloop_edges(topology))
    frame["in_degree"] = pd.Series(dict(topology.in_degree()))
    frame["out_degree"] = pd.Series(dict(topology.out_degree()))
    frame["unique_senders"] = frame.in_degree
    frame["unique_receivers"] = frame.out_degree
    frame["total_degree"] = frame.in_degree + frame.out_degree
    frame["is_boundary_node"] = frame.depth.ge(4)
    frame["observed_net"] = frame.sum_in - frame.sum_out
    frame["flow_through_ratio"] = safe_divide(frame.sum_out, frame.sum_in)
    frame["flow_ratio_reliable"] = ~frame.is_seed & frame.sum_in.gt(0)
    frame["retention_ratio"] = safe_divide((frame.sum_in - frame.sum_out).clip(lower=0), frame.sum_in)
    frame["fan_in_ratio"] = safe_divide(frame.in_degree, frame.total_degree).fillna(0)
    frame["fan_out_ratio"] = safe_divide(frame.out_degree, frame.total_degree).fillna(0)
    frame["pagerank"] = pd.Series(nx.pagerank(topology, weight="sum_kzt", max_iter=500, tol=1e-9))
    sample = min(betweenness_samples, len(topology)) if len(topology) > exact_limit else None
    frame["betweenness"] = pd.Series(nx.betweenness_centrality(topology, k=sample, seed=random_seed, weight=None))
    for label, values in (("degree_centrality", nx.degree_centrality(topology)),
                          ("in_degree_centrality", nx.in_degree_centrality(topology)),
                          ("out_degree_centrality", nx.out_degree_centrality(topology))):
        frame[label] = pd.Series(values)
    components = sorted(nx.weakly_connected_components(topology), key=lambda group: (-len(group), min(group)))
    component_map = {node: index for index, group in enumerate(components) for node in group}
    frame["weak_component_id"] = pd.Series(component_map)
    frame["component_size"] = frame.weak_component_id.map({i: len(group) for i, group in enumerate(components)})
    frame["cluster_id"] = pd.Series(cluster_map)
    seeds = set(frame.index[frame.is_seed])
    reach = dict.fromkeys(topology, 0)
    distance: dict = {}
    for seed in sorted(seeds):
        for node, length in nx.single_source_shortest_path_length(topology, seed).items():
            reach[node] += 1
            distance[node] = min(distance.get(node, length), length)
    frame["seed_reach"] = pd.Series(reach)
    frame["minimum_distance_from_seed"] = pd.Series(distance, dtype=float)
    articulation = set(nx.articulation_points(topology.to_undirected()))
    records = []
    for gid in frame.index:
        predecessors, successors = set(topology.predecessors(gid)), set(topology.successors(gid))
        neighbors = predecessors | successors
        counts = Counter(cluster_map[neighbor] for neighbor in neighbors)
        participation = 1 - sum((count / len(neighbors)) ** 2 for count in counts.values()) if neighbors else 0
        records.append({
            "gid": gid, "number_seed_predecessors": len(predecessors & seeds),
            "number_seed_neighbors": len(neighbors & seeds), "predecessor_count": len(predecessors),
            "successor_count": len(successors), "upstream_diversity": len({cluster_map[n] for n in predecessors}),
            "downstream_diversity": len({cluster_map[n] for n in successors}),
            "community_neighbors_count": len(counts), "participation_coefficient": participation,
            "is_articulation": gid in articulation,
            "two_hop_reach": len(nx.single_source_shortest_path_length(topology, gid, cutoff=2)) - 1,
        })
    return frame.join(pd.DataFrame(records).set_index("gid")).join(temporal_features(nodes, transactions).set_index("gid")).reset_index()
