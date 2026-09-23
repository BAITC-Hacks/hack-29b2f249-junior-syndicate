from src.scoring import assign_roles, assign_priority
from src.workspace import graph_view, network_figure, ranked_nodes


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
