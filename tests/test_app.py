from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def test_ui_search_boundary_isolate_cluster_and_filters():
    if not (ROOT / "output/node_features.csv").exists():
        pytest.skip("Run pipeline first for UI integration test")
    data = pd.read_csv(ROOT / "output/node_features.csv")
    app = AppTest.from_file(str(ROOT / "app/app.py"), default_timeout=60).run()
    assert not app.exception
    boundary = str(int(data[data.is_boundary_node].gid.iloc[0]))
    isolated = str(int(data[data.total_degree.eq(0)].gid.iloc[0]))
    app.selectbox(key="gid").select(boundary).run()
    assert not app.exception
    assert any(boundary in value.value for value in app.subheader)
    app.selectbox(key="gid").select(isolated).run()
    assert not app.exception
    app.selectbox(key="mode").select("Кластер").run()
    app.radio(key="color").set_value("Кластер").run()
    app.selectbox(key="rank_role").select("consolidator").run()
    assert not app.exception


def test_ui_missing_output_has_helpful_state(tmp_path, monkeypatch):
    monkeypatch.setenv("MONEY_GRAPH_OUTPUT", str(tmp_path))
    app = AppTest.from_file(str(ROOT / "app/app.py"), default_timeout=30).run()
    assert not app.exception
    assert "python run.py" in app.info[0].value
