from copy import deepcopy

import networkx as nx
import numpy as np
import pandas as pd
import pytest

from src.features import calculate_features
from src.graph_builder import build_graph, communities
from src.load_data import InputData, validate_data
from src.resilience import assess_resilience, assess_ranking_stability
from src.scoring import assign_roles, assign_priority


def test_path_center_removal_and_reproducibility():
    graph = nx.DiGraph([(1, 2), (2, 3), (3, 4), (4, 5)])
    result = assess_resilience(graph, [3, 2, 4, 1, 5], removal_counts=(1,))
    top = result[result.strategy.eq("top_priority")].iloc[0]
    assert top.components_mean == 2
    assert top.largest_component_remaining_fraction == .5
    assert top.fragmentation_increase == 1
    pd.testing.assert_frame_equal(result, assess_resilience(graph, [3, 2, 4, 1, 5], removal_counts=(1,)))


def test_stability_is_reproducible_and_preserves_inputs(sample_data, features, config):
    graph = build_graph(sample_data.nodes, sample_data.edges)
    original_graph, original_config = deepcopy(graph), deepcopy(config)
    original_features = features.copy(deep=True)
    original_tables = [getattr(sample_data, name).copy(deep=True) for name in ("nodes", "edges", "transactions")]
    scenarios, nodes = assess_ranking_stability(sample_data, graph, features, config)
    repeated = assess_ranking_stability(sample_data, graph, features.iloc[::-1], config)
    pd.testing.assert_frame_equal(scenarios, repeated[0])
    pd.testing.assert_frame_equal(nodes, repeated[1])
    pd.testing.assert_frame_equal(features, original_features)
    for name, original in zip(("nodes", "edges", "transactions"), original_tables):
        pd.testing.assert_frame_equal(getattr(sample_data, name), original)
    assert config == original_config and nx.utils.graphs_equal(graph, original_graph)
    assert scenarios.kind.value_counts().to_dict() == {"priority_weights": 12, "community_resolution": 2, "baseline": 1}
    np.testing.assert_allclose(scenarios.filter(like="weight__").sum(axis=1), 1)
    assert scenarios.n_nodes.eq(len(features)).all() and scenarios.top_n.eq(20).all()
    assert scenarios[scenarios.kind.eq("priority_weights")].role_changes.eq(0).all()
    assert not nodes.duplicated(["kind", "gid"]).any()
    for kind, count in (("priority_weights", 12), ("community_resolution", 2)):
        group = nodes[nodes.kind.eq(kind)]
        assert set(group.gid) == set(features.gid)
        assert group.scenario_count.eq(count).all()
        assert group.top_n_hits.sum() == 20 * count
        np.testing.assert_allclose(group.top_n_fraction, group.top_n_hits / count)
        assert group.best_rank.le(group.worst_rank).all()
        assert group[group.gid.eq(900)].top_n_hits.item() == 0


def test_stability_weight_results_match_independent_rescoring(sample_data, features, config):
    graph = build_graph(sample_data.nodes, sample_data.edges)
    scenarios, nodes = assess_ranking_stability(sample_data, graph, features, config)
    base = assign_priority(assign_roles(features, config), config).sort_values(["priority_score", "gid"], ascending=[False, True])
    base_ids = base.gid.head(20).tolist()
    expected_ranks = []
    for row in scenarios[scenarios.kind.eq("priority_weights")].itertuples():
        changed = deepcopy(config)
        changed["priority"][row.parameter] *= row.multiplier
        total = sum(changed["priority"].values())
        changed["priority"] = {key: value / total for key, value in changed["priority"].items()}
        for factor, weight in changed["priority"].items():
            assert getattr(row, f"weight__{factor}") == pytest.approx(weight)
        ranked = assign_priority(assign_roles(features, changed), changed).sort_values(["priority_score", "gid"], ascending=[False, True])
        ids = ranked.gid.head(20).tolist()
        assert row.overlap_count == len(set(base_ids) & set(ids))
        assert row.entered_gids == ", ".join(str(gid) for gid in ids if gid not in base_ids)
        assert row.left_gids == ", ".join(str(gid) for gid in base_ids if gid not in ids)
        expected_ranks.append(pd.Series(range(1, len(ranked) + 1), index=ranked.gid))
    matrix = pd.concat(expected_ranks, axis=1)
    actual = nodes[nodes.kind.eq("priority_weights")].set_index("gid").reindex(matrix.index)
    np.testing.assert_array_equal(actual.best_rank, matrix.min(axis=1))
    np.testing.assert_array_equal(actual.worst_rank, matrix.max(axis=1))
    np.testing.assert_array_equal(actual.top_n_hits, matrix.le(20).sum(axis=1))


def test_stability_recomputes_cluster_features_and_roles(sample_data, features, config, monkeypatch):
    graph = build_graph(sample_data.nodes, sample_data.edges)
    calls = []
    role_inputs = []
    def calculate(nodes, edges, transactions, topology, cluster_map, samples, limit, seed):
        frame = calculate_features(nodes, edges, transactions, topology, cluster_map, samples, limit, seed)
        calls.append((cluster_map, samples, limit, seed, frame))
        return frame
    def roles(frame, settings):
        role_inputs.append(frame)
        return assign_roles(frame, settings)
    monkeypatch.setattr("src.resilience.calculate_features", calculate)
    monkeypatch.setattr("src.resilience.assign_roles", roles)
    scenarios, nodes = assess_ranking_stability(sample_data, graph, features, config)
    base = assign_priority(assign_roles(features, config), config).set_index("gid")
    assert len(calls) == 2
    assert len(role_inputs) == 3 and role_inputs[0] is features
    assert all(actual is call[4] for actual, call in zip(role_inputs[1:], calls))
    ranks, changes = [], []
    for row, call in zip(scenarios[scenarios.kind.eq("community_resolution")].itertuples(), calls):
        assert row.community_resolution == config["community_resolution"] * row.multiplier
        assert call[0] == communities(graph, config["random_seed"], row.community_resolution)
        assert call[1:4] == (config["betweenness_samples"], config["betweenness_exact_limit"], config["random_seed"])
        scored = assign_priority(assign_roles(call[4], config), config).sort_values(["priority_score", "gid"], ascending=[False, True]).set_index("gid")
        ranks.append(pd.Series(range(1, len(scored) + 1), index=scored.index))
        changes.append(scored.role.reindex(base.index).ne(base.role))
        assert row.role_changes == int(changes[-1].sum())
        assert row.n_clusters == scored.cluster_id.nunique()
    actual = nodes[nodes.kind.eq("community_resolution")].set_index("gid").reindex(base.index)
    np.testing.assert_array_equal(actual.top_n_hits, pd.concat(ranks, axis=1).reindex(base.index).le(20).sum(axis=1))
    np.testing.assert_array_equal(actual.role_change_count, pd.concat(changes, axis=1).sum(axis=1))


def test_stability_detects_rank_swap_and_preserves_large_gids(config, monkeypatch):
    ids = [100_000_000_000_000_001, 100_000_000_000_000_002]
    features = pd.DataFrame({"gid": ids, "role": ["peripheral"] * 2, "cluster_id": [0, 1],
                             "structural": [1.0, 0.0], "financial": [0.0, 1.24]})
    data = InputData(pd.DataFrame(), features[["gid"]], pd.DataFrame())
    graph = nx.DiGraph()
    graph.add_nodes_from(ids)
    monkeypatch.setattr("src.resilience.assign_roles", lambda frame, config: frame.copy())
    monkeypatch.setattr("src.resilience.assign_priority", lambda frame, config: frame.assign(
        priority_score=frame.structural * config["priority"]["structural"] + frame.financial * config["priority"]["financial"]))
    monkeypatch.setattr("src.resilience.calculate_features", lambda *args: features.copy())
    scenarios, nodes = assess_ranking_stability(data, graph, features.iloc[::-1], config, top_n=1)
    swapped = scenarios[scenarios.overlap_count.eq(0)]
    assert set(swapped.scenario) == {"priority__structural__0.9", "priority__financial__1.1"}
    assert swapped.entered_gids.eq(str(ids[1])).all() and swapped.left_gids.eq(str(ids[0])).all()
    assert swapped.overlap_fraction.eq(0).all() and swapped.max_abs_rank_shift_base_top.eq(1).all()
    weights = nodes[nodes.kind.eq("priority_weights")].set_index("gid")
    assert weights.loc[ids[0], "baseline_rank"] == 1 and weights.loc[ids[0], "top_n_hits"] == 10
    assert weights.loc[ids[1], "baseline_rank"] == 2 and weights.loc[ids[1], "top_n_hits"] == 2
    assert weights.best_rank.eq(1).all() and weights.worst_rank.eq(2).all()


@pytest.mark.parametrize("top_n", [2, 20])
def test_stability_handles_isolates_ties_and_small_graphs(sample_data, config, top_n):
    data = validate_data(sample_data.edges.iloc[:0], sample_data.nodes.iloc[:3], sample_data.transactions.iloc[:0])
    graph = build_graph(data.nodes, data.edges)
    features = calculate_features(data.nodes, data.edges, data.transactions, graph, communities(graph))
    scenarios, nodes = assess_ranking_stability(data, graph, features, config, top_n=top_n)
    assert scenarios.top_n.eq(min(top_n, 3)).all()
    assert scenarios.overlap_fraction.eq(1).all()
    assert scenarios.positive_score_nodes.eq(0).all() and scenarios.cutoff_score.eq(0).all()
    assert scenarios.cutoff_tied_nodes.eq(3).all()
    assert scenarios.cutoff_tie_crosses_top_n.eq(top_n < 3).all()
    assert nodes.max_abs_rank_shift.eq(0).all()
    assert nodes[nodes.kind.eq("priority_weights")].gid.tolist() == sorted(data.nodes.gid)


@pytest.mark.parametrize("top_n", [0, -1, True, 1.5])
def test_stability_rejects_invalid_top_size(sample_data, features, config, top_n):
    with pytest.raises(ValueError, match="positive integer"):
        assess_ranking_stability(sample_data, build_graph(sample_data.nodes, sample_data.edges), features, config, top_n)
