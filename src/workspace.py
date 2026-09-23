"""Read-side queries and graph rendering shared by UI and tests."""
from __future__ import annotations

import math
from pathlib import Path
import json

import networkx as nx
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from .scoring import ROLE_COLORS


def load_workspace(directory: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    features = pd.read_csv(directory / "node_features.csv", dtype={"gid": "int64"})
    edges = pd.read_csv(directory / "graph_edges.csv", dtype={"src": "int64", "dst": "int64"})
    clusters = pd.read_csv(directory / "clusters.csv")
    summary = json.loads((directory / "run_summary.json").read_text(encoding="utf-8"))
    return features, edges, clusters, summary


def ranked_nodes(features: pd.DataFrame, role: str | None = None, cluster: int | None = None) -> pd.DataFrame:
    selected = features
    if role:
        selected = selected[selected.role.eq(role)]
    if cluster is not None:
        selected = selected[selected.cluster_id.eq(cluster)]
    return selected.sort_values(["priority_score", "gid"], ascending=[False, True]).reset_index(drop=True)


def graph_view(features: pd.DataFrame, edges: pd.DataFrame, mode: str, gid: int, cluster: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    if mode == "Окрестность GID":
        related = edges[edges.src.eq(gid) | edges.dst.eq(gid)]
        ids = {gid, *related.src, *related.dst}
        nodes = features[features.gid.isin(ids)]
    elif mode == "Кластер":
        nodes = features[features.cluster_id.eq(cluster)]
    elif mode == "Крупнейшая компонента":
        largest = features.weak_component_id.value_counts().idxmax()
        nodes = features[features.weak_component_id.eq(largest)]
    else:
        nodes = features
    visible_edges = edges[edges.src.isin(nodes.gid) & edges.dst.isin(nodes.gid)]
    return nodes, visible_edges


def counterparties(edges: pd.DataFrame, gid: int, direction: str) -> pd.DataFrame:
    endpoint, other = ("dst", "src") if direction == "in" else ("src", "dst")
    return edges[edges[endpoint].eq(gid)][[other, "sum_kzt", "n_tx"]].sort_values("sum_kzt", ascending=False).rename(columns={other: "gid"})


def network_figure(nodes: pd.DataFrame, edges: pd.DataFrame, selected_gid: int, color_by: str = "role") -> go.Figure:
    graph = nx.Graph()
    graph.add_nodes_from(sorted(nodes.gid.tolist()))
    graph.add_edges_from((row.src, row.dst) for row in edges.itertuples() if row.src != row.dst)
    positions = nx.spring_layout(graph, seed=42, iterations=35, weight=None)
    figure = go.Figure()
    arrow_x, arrow_y, arrow_angle, edge_text = [], [], [], []
    positive = edges[edges.src.ne(edges.dst)]
    bucket_ids = np.minimum(np.floor(np.log1p(positive.sum_kzt) / max(np.log1p(positive.sum_kzt).max(), 1) * 3), 2).astype(int) if not positive.empty else []
    for bucket in range(3):
        line_x, line_y = [], []
        selected_edges = positive.loc[np.asarray(bucket_ids) == bucket] if len(positive) else positive
        for edge in selected_edges.itertuples():
            start, end = positions[edge.src], positions[edge.dst]
            line_x.extend([start[0], end[0], None])
            line_y.extend([start[1], end[1], None])
            arrow_x.append(start[0] + .78 * (end[0] - start[0]))
            arrow_y.append(start[1] + .78 * (end[1] - start[1]))
            arrow_angle.append(math.degrees(math.atan2(end[0] - start[0], end[1] - start[1])))
            edge_text.append(f"{edge.src} → {edge.dst}<br>{edge.sum_kzt:,.0f} KZT · {edge.n_tx} переводов")
        figure.add_trace(go.Scattergl(x=line_x, y=line_y, mode="lines", line={"width": .5 + bucket * .55, "color": "#64748b"}, opacity=.4, hoverinfo="skip", showlegend=False))
    figure.add_trace(go.Scatter(x=arrow_x, y=arrow_y, mode="markers", marker={"symbol": "triangle-up", "size": 6, "angle": arrow_angle, "color": "#94a3b8"}, text=edge_text, hovertemplate="%{text}<extra></extra>", showlegend=False))
    labeled = set(nodes.nlargest(3, "priority_score").gid) | {selected_gid}
    for group, members in nodes.groupby(color_by):
        custom = [[str(row.gid), row.role, f"{row.role_score:.3f}", f"{row.priority_score:.3f}",
                   str(row.cluster_id), str(row.depth), str(row.in_degree), str(row.out_degree),
                   f"{row.sum_in:,.0f}", f"{row.sum_out:,.0f}"] for row in members.itertuples()]
        color = ROLE_COLORS.get(group) if color_by == "role" else f"hsl({(int(group) * 137) % 360},65%,55%)"
        figure.add_trace(go.Scattergl(
            x=[positions[gid][0] for gid in members.gid], y=[positions[gid][1] for gid in members.gid],
            mode="markers+text", name=str(group), customdata=custom,
            text=[str(gid) if gid in labeled else "" for gid in members.gid], textposition="top center",
            textfont={"size": 10}, marker={"size": (8 + 18 * members.priority_score).tolist(), "color": color,
                                          "line": {"width": [3 if gid == selected_gid else 0 for gid in members.gid], "color": "#f8fafc"}},
            hovertemplate="GID %{customdata[0]}<br>%{customdata[1]} · обоснованность %{customdata[2]}<br>Приоритет %{customdata[3]} · кластер %{customdata[4]}<br>Depth %{customdata[5]} · вход/выход %{customdata[6]}/%{customdata[7]}<br>Вход %{customdata[8]} · выход %{customdata[9]} KZT<extra></extra>",
        ))
    figure.update_layout(height=560, margin={"l": 10, "r": 10, "t": 25, "b": 10},
                         xaxis={"visible": False}, yaxis={"visible": False, "scaleanchor": "x"},
                         legend={"orientation": "h", "y": 1.07}, hovermode="closest",
                         paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return figure
