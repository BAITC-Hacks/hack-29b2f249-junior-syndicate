import numpy as np
import pandas as pd

from src.features import temporal_features, calculate_features
from src.graph_builder import build_graph, communities
from src.load_data import validate_data


def test_transaction_statistics_use_individual_payments():
    nodes = pd.DataFrame({"gid": [1, 2, 3], "depth": [0, 1, 0], "is_seed": [True, False, True]})
    tx = pd.DataFrame({"src": [1, 1, 3], "dst": [2, 2, 2], "date": ["2026-07-01"]*3, "sum_kzt": [5000, 10000, 30000]})
    edges = tx.groupby(["src", "dst"], as_index=False).agg(sum_kzt=("sum_kzt", "sum"), n_tx=("sum_kzt", "size"))
    edges["depth"] = 1
    data = validate_data(edges, nodes, tx)
    graph = build_graph(data.nodes, data.edges)
    f = calculate_features(data.nodes, data.edges, data.transactions, graph, communities(graph)).set_index("gid")
    assert f.loc[2, "avg_in_tx"] == 15000
    assert f.loc[2, "median_in_tx"] == 10000
    assert f.loc[2, "max_in_tx"] == 30000
    assert f.loc[2, "seed_reach"] == 2
    assert f.loc[2, "minimum_distance_from_seed"] == 1
    assert np.isnan(f.loc[1, "flow_through_ratio"])


def test_fifo_is_amount_limited_and_does_not_reuse_outflow():
    nodes = pd.DataFrame({"gid": [2]})
    tx = pd.DataFrame({"src": [1, 3, 2], "dst": [2, 2, 4], "sum_kzt": [10000, 10000, 5000],
                       "date": pd.to_datetime(["2026-07-01", "2026-07-01", "2026-07-02"], utc=True)})
    result = temporal_features(nodes, tx).iloc[0]
    assert result.forwarded_within_24h_ratio == .25
    assert result.forwarded_within_48h_ratio == .25


def test_fifo_excludes_equal_or_earlier_timestamps_and_self_transfers():
    nodes = pd.DataFrame({"gid": [2]})
    tx = pd.DataFrame({"src": [2, 1, 2, 2], "dst": [3, 2, 3, 2], "sum_kzt": [50000]*4,
                       "date": pd.to_datetime(["2026-07-01", "2026-07-02", "2026-07-02", "2026-07-03"], utc=True)})
    result = temporal_features(nodes, tx).iloc[0]
    assert result.forwarded_within_48h_ratio == 0


def test_fifo_distinguishes_24_and_48_hours():
    nodes = pd.DataFrame({"gid": [2]})
    tx = pd.DataFrame({"src": [1, 2], "dst": [2, 3], "sum_kzt": [10000, 10000],
                       "date": pd.to_datetime(["2026-07-01 00:00", "2026-07-02 12:00"], utc=True)})
    result = temporal_features(nodes, tx).iloc[0]
    assert result.forwarded_within_24h_ratio == 0
    assert result.forwarded_within_48h_ratio == 1


def test_community_determinism_and_isolates(sample_data):
    graph = build_graph(sample_data.nodes, sample_data.edges)
    reversed_graph = build_graph(sample_data.nodes.iloc[::-1], sample_data.edges.iloc[::-1])
    assert communities(graph) == communities(reversed_graph)
    assert len(communities(graph)) == len(sample_data.nodes)
    isolates = build_graph(sample_data.nodes, sample_data.edges.iloc[:0])
    assert len(set(communities(isolates).values())) == len(sample_data.nodes)
