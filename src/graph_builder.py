"""Stable directed topology and weighted Louvain communities."""
from __future__ import annotations

import math
import networkx as nx
import pandas as pd


def build_graph(nodes: pd.DataFrame, edges: pd.DataFrame) -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_nodes_from(sorted(nodes.gid.tolist()))
    for row in edges.sort_values(["src", "dst"]).itertuples(index=False):
        if graph.has_edge(row.src, row.dst):
            graph[row.src][row.dst]["sum_kzt"] += float(row.sum_kzt)
            graph[row.src][row.dst]["n_tx"] += int(row.n_tx)
        else:
            graph.add_edge(row.src, row.dst, sum_kzt=float(row.sum_kzt), n_tx=int(row.n_tx))
    return graph


def communities(graph: nx.DiGraph, seed: int = 42, resolution: float = 1.0) -> dict[int, int]:
    undirected = nx.Graph()
    undirected.add_nodes_from(sorted(graph.nodes))
    for source, target, data in sorted(graph.edges(data=True)):
        if source == target:
            continue
        existing = undirected.get_edge_data(source, target, {}).get("amount", 0)
        undirected.add_edge(source, target, amount=existing + data["sum_kzt"])
    for _, _, data in undirected.edges(data=True):
        data["weight"] = math.log1p(data["amount"])
    isolates = set(nx.isolates(undirected))
    active = undirected.subgraph([node for node in undirected if node not in isolates])
    groups = nx.community.louvain_communities(active, weight="weight", seed=seed, resolution=resolution) if active.number_of_edges() else []
    groups.extend({node} for node in isolates)
    groups.sort(key=lambda group: (-len(group), min(group)))
    return {node: cluster_id for cluster_id, group in enumerate(groups) for node in sorted(group)}
