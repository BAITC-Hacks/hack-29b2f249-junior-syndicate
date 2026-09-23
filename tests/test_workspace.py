from src.scoring import assign_roles, assign_priority
from src.workspace import graph_view, network_figure, ranked_nodes
from src.workspace import workspace_payload, node_dossier, simulation_payload
from src.pipeline import cluster_export
from src.scoring import generate_evidence


def test_map_ego_and_large_gid_strings(features, sample_data, config):
    nodes = assign_priority(assign_roles(features, config), config)
    visible, edges = graph_view(nodes, sample_data.edges, "Окрестность GID", 100, 0)
    assert len(visible) == 21 and len(edges) == 20
    shift = 100_000_000_000_000_001
    visible = visible.assign(gid=visible.gid + shift)
    edges = edges.assign(src=edges.src + shift, dst=edges.dst + shift)
    figure = network_figure(visible, edges, shift + 100)
    payload = figure.to_json()
    assert str(shift + 100) in payload
    assert all(isinstance(row[0], str) for trace in figure.data if trace.customdata is not None for row in trace.customdata)
    assert any(trace.marker.symbol == "triangle-up" for trace in figure.data if trace.type == "scatter")


def test_rank_filters_and_isolated_map(features, sample_data, config):
    nodes = assign_priority(assign_roles(features, config), config)
    ranked = ranked_nodes(nodes, role="consolidator")
    assert ranked.role.eq("consolidator").all()
    assert ranked.priority_score.is_monotonic_decreasing
    visible, edges = graph_view(nodes, sample_data.edges, "Окрестность GID", 900, 0)
    assert len(visible) == 1 and edges.empty
    assert network_figure(visible, edges, 900).data


def test_browser_payload_preserves_identifiers_and_observed_totals(features, sample_data, config):
    import json

    nodes = assign_priority(assign_roles(features, config), config)
    nodes["evidence"] = nodes.apply(generate_evidence, axis=1)
    shift = 100_000_000_000_000_001
    nodes["gid"] += shift
    edges = sample_data.edges.assign(src=sample_data.edges.src + shift, dst=sample_data.edges.dst + shift)
    clusters = cluster_export(nodes, edges)
    payload = workspace_payload(nodes, edges, clusters, {"nodes": len(nodes), "input_directory": "private path"})
    json.dumps(payload, allow_nan=False)
    assert {n["gid"] for n in payload["nodes"]} == set(nodes.gid.astype(str))
    assert all(isinstance(e["src"], str) and isinstance(e["dst"], str) for e in payload["edges"])
    assert sum(f["sum_kzt"] for f in payload["role_flows"]) == edges.sum_kzt.sum()
    assert "input_directory" not in payload["summary"]
    card = node_dossier(nodes, edges, str(900 + shift))
    assert card["gid"] == str(900 + shift)
    assert card["in"] == [] and card["out"] == []
    assert ranked_nodes(nodes, query=str(900 + shift)).gid.tolist() == [900 + shift]


def test_simulation_uses_ranked_nodes_and_counts_all_remaining_nodes(features, sample_data, config):
    nodes = assign_priority(assign_roles(features, config), config)
    result = simulation_payload(nodes, sample_data.edges, 5)
    assert result["removed"] == ranked_nodes(nodes).gid.head(5).astype(str).tolist()
    assert sum(result["sizes"]) == len(nodes) - 5
    top = next(r for r in result["results"] if r["strategy"] == "top_priority")
    assert result["sizes"][0] == top["largest_component_mean"]
    assert len(result["sizes"]) == top["components_mean"]
