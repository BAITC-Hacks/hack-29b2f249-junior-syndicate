import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.pipeline import run, explain_node, ROLE_COLUMNS, TOP_COLUMNS, CLUSTER_COLUMNS
from src.scoring import ROLES

ROOT = Path(__file__).resolve().parents[1]


def test_end_to_end_parquet_exports_and_large_ids(sample_data, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    shift = 100_000_000_000_000_001
    for name in ("nodes", "edges", "transactions"):
        frame = getattr(sample_data, name).copy()
        for column in ("gid", "src", "dst"):
            if column in frame:
                frame[column] += shift
        frame.to_parquet(data_dir / f"{name}.parquet", index=False)
    out = tmp_path / "out"
    result = run(data_dir, out)
    assert not (out / "ranking_stability_scenarios.csv").exists()
    roles = pd.read_csv(out / "nodes_roles.csv")
    clusters = pd.read_csv(out / "clusters.csv")
    top = pd.read_csv(out / "top_nodes.csv")
    assert roles.columns.tolist() == ROLE_COLUMNS
    assert top.columns.tolist() == TOP_COLUMNS
    assert clusters.columns.tolist() == CLUSTER_COLUMNS
    assert len(roles) == len(sample_data.nodes)
    assert set(roles.gid) == set(sample_data.nodes.gid + shift)
    assert set(roles.role) <= set(ROLES)
    assert roles.evidence.str.len().between(1, 200).all()
    assert len(top) >= 20 and top.priority_score.is_monotonic_decreasing
    assert clusters.sum_kzt_internal.sum() <= sample_data.edges.sum_kzt.sum()
    card = explain_node(shift + 300, out)
    assert card["gid"] == shift + 300
    assert card["role"] == "transit"
    assert card["metrics"]["sum_in"] == 1_000_000
    assert np.isclose(sum(item["contribution"] for item in card["priority_factors"]), card["priority_score"])
    assert card["limitations"] and card["role_factors"]
    repeated = run(data_dir, tmp_path / "repeat")
    pd.testing.assert_frame_equal(result, repeated)
    assert json.loads((out / "run_summary.json").read_text(encoding="utf-8"))["boundary_terminals"] == 0


def test_real_data_invariants_and_starter_parity():
    from starter.starter import build_graph, basic_features, load
    if not (ROOT / "data/nodes.parquet").exists():
        import pytest
        pytest.skip("Organizer parquet not present")
    edges, nodes, tx = load(ROOT / "data")
    baseline = basic_features(build_graph(edges), nodes).set_index("gid")
    from src.graph_builder import build_graph as build_full_graph, communities
    from src.features import calculate_features
    from src.load_data import load_data
    data = load_data(ROOT / "data")
    graph = build_full_graph(data.nodes, data.edges)
    actual = calculate_features(data.nodes, data.edges, data.transactions, graph, communities(graph)).set_index("gid")
    for ours, reference in (("in_degree", "in_deg"), ("out_degree", "out_deg"), ("sum_in", "in_kzt"), ("sum_out", "out_kzt"), ("n_in_tx", "in_tx"), ("n_out_tx", "out_tx")):
        np.testing.assert_allclose(actual.loc[baseline.index, ours], baseline[reference])
    assert len(actual) == 2248
    assert actual.is_seed.sum() == 81
    assert actual.total_degree.eq(0).sum() == 19
    assert actual.weak_component_id.nunique() == 35
    assert ((actual.depth == 4) & (actual.out_degree == 0)).sum() == 444


def test_only_isolates_pipeline(sample_data, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for name in ("nodes", "edges", "transactions"):
        frame = getattr(sample_data, name)
        (frame if name == "nodes" else frame.iloc[:0]).to_parquet(data_dir / f"{name}.parquet", index=False)
    result = run(data_dir, tmp_path / "out")
    assert result.role.eq("peripheral").all()
    assert result.priority_score.eq(0).all()


def test_optional_stability_report_preserves_baseline_exports(sample_data, tmp_path):
    import hashlib

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for name in ("nodes", "edges", "transactions"):
        getattr(sample_data, name).to_parquet(data_dir / f"{name}.parquet", index=False)
    out = tmp_path / "out"
    baseline = run(data_dir, out)
    before = {name: (out / name).read_bytes() for name in ("nodes_roles.csv", "clusters.csv", "top_nodes.csv")}
    checked = run(data_dir, out, check_stability=True)
    pd.testing.assert_frame_equal(baseline, checked)
    for name, content in before.items():
        assert (out / name).read_bytes() == content
    summary = json.loads((out / "run_summary.json").read_text(encoding="utf-8"))
    assert summary["ranking_stability"]["perturbations"] == 14
    assert summary["ranking_stability"]["top_n"] == 20
    scenarios = pd.read_csv(out / "ranking_stability_scenarios.csv")
    nodes = pd.read_csv(out / "ranking_stability_nodes.csv")
    assert len(scenarios) == 15 and len(nodes) == 2 * len(sample_data.nodes)
    report = (out / "ranking_stability_report.md").read_text(encoding="utf-8")
    assert "не оценка точности" in report and "Базовый сценарий исключён" in report
    for name in ("nodes", "edges", "transactions"):
        assert hashlib.sha256((data_dir / f"{name}.parquet").read_bytes()).hexdigest() in report


def test_stability_cli_flag_is_forwarded(monkeypatch, tmp_path):
    from src.pipeline import main
    from unittest.mock import Mock

    execute = Mock()
    monkeypatch.setattr("src.pipeline.run", execute)
    monkeypatch.setattr("sys.argv", ["run.py", "--data", str(tmp_path), "--out", str(tmp_path / "out"), "--check-stability"])
    main()
    assert execute.call_args.args[:2] == (tmp_path, tmp_path / "out")
    assert execute.call_args.kwargs == {"check_stability": True}


def test_cli_help_works_with_windows_console_encoding(monkeypatch):
    import io
    import pytest
    from src.pipeline import main

    buffer = io.BytesIO()
    output = io.TextIOWrapper(buffer, encoding="cp1251")
    monkeypatch.setattr("sys.stdout", output)
    monkeypatch.setattr("sys.argv", ["run.py", "--help"])
    with pytest.raises(SystemExit) as result:
        main()
    output.flush()
    assert result.value.code == 0
    assert b"--check-stability" in buffer.getvalue()
