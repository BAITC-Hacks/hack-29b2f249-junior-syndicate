import networkx as nx
import pandas as pd

from src.resilience import assess_resilience


def test_path_center_removal_and_reproducibility():
    graph = nx.DiGraph([(1, 2), (2, 3), (3, 4), (4, 5)])
    result = assess_resilience(graph, [3, 2, 4, 1, 5], removal_counts=(1,))
    top = result[result.strategy.eq("top_priority")].iloc[0]
    assert top.components_mean == 2
    assert top.largest_component_remaining_fraction == .5
    assert top.fragmentation_increase == 1
    pd.testing.assert_frame_equal(result, assess_resilience(graph, [3, 2, 4, 1, 5], removal_counts=(1,)))
