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


def test_ai_context_is_bounded_grounded_and_preserves_large_ids(features, sample_data, config):
    import json
    from src.pipeline import explain_node
    from src.workspace import node_ai_context
    nodes = assign_priority(assign_roles(features, config), config)
    nodes["evidence"] = "Синтетические данные"
    shift = 100_000_000_000_000_001
    nodes["gid"] += shift
    edges = sample_data.edges.assign(src=sample_data.edges.src + shift, dst=sample_data.edges.dst + shift)
    card = explain_node(shift + 100, features=nodes)
    context = node_ai_context(card, edges)
    assert context["gid"] == str(shift + 100)
    assert context["metrics"]["pagerank"] == card["metrics"]["pagerank"]
    assert context["metrics"]["betweenness"] == card["metrics"]["betweenness"]
    assert context["links"]["in"]["total"] == 20
    assert context["links"]["in"]["omitted"] == 15
    assert len(context["links"]["in"]["largest_by_amount"]) == 5
    assert all(isinstance(row["gid"], str) for row in context["links"]["in"]["largest_by_amount"])
    assert context["limitations"] == card["limitations"]
    assert "transactions" not in context and "edges" not in context
    json.dumps(context, allow_nan=False)
    isolate = node_ai_context(explain_node(shift + 900, features=nodes), edges)
    assert isolate["links"]["in"]["total"] == 0
    assert isolate["metrics"]["flow_through_ratio"] is None
    assert any("Seed" in text for text in isolate["limitations"])
    boundary = node_ai_context(explain_node(shift + 500, features=nodes), edges)
    assert any("depth=4" in text for text in boundary["limitations"])


def test_ai_request_and_structured_response_do_not_change_input(monkeypatch):
    import io
    import json
    from copy import deepcopy
    from src.workspace import explain_with_ai
    payload = {"gid": "100000000000000001", "role": "consolidator", "priority_score": .8}
    original = deepcopy(payload)
    expected = {"summary": "Гипотеза для проверки", "reasons": ["Наблюдаемые метрики"], "limitations": ["Неполные данные"]}
    calls = []
    def respond(request, timeout, context):
        import ssl
        assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
        assert context.cert_store_stats()["x509_ca"] > 0
        calls.append(request)
        body = json.loads(request.data)
        assert json.loads(body["input"]) == payload
        assert body["store"] is False and timeout == 25
        assert body["text"]["format"]["strict"] is True
        assert request.full_url == "https://api.openai.com/v1/responses"
        return io.BytesIO(json.dumps({"status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": json.dumps(expected)}]}]}).encode())
    monkeypatch.setattr("src.workspace.urlopen", respond)
    assert explain_with_ai(payload, "test-key") == expected
    assert len(calls) == 1 and payload == original


def test_ai_failures_are_safe_and_missing_key_never_calls_network(monkeypatch):
    import io
    import json
    import pytest
    from urllib.error import URLError
    from src.workspace import explain_with_ai
    calls = []
    def unavailable(*args, **kwargs):
        calls.append(1)
        raise URLError("private upstream detail")
    monkeypatch.setattr("src.workspace.urlopen", unavailable)
    with pytest.raises(ValueError):
        explain_with_ai({}, "")
    assert not calls
    with pytest.raises(RuntimeError) as failure:
        explain_with_ai({}, "test-key")
    assert "private" not in str(failure.value) and "test-key" not in str(failure.value)
    assert len(calls) == 1
    for response in (
        None, [], {"status": "incomplete"},
        {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal"}]}]},
        {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "{}"}]}]},
        {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "not JSON"}]}]},
    ):
        monkeypatch.setattr("src.workspace.urlopen", lambda *args, **kwargs: io.BytesIO(json.dumps(response).encode()))
        with pytest.raises(RuntimeError):
            explain_with_ai({}, "test-key")
