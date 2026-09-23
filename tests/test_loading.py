import numpy as np
import pytest

from src.load_data import load_data, validate_data


def test_missing_files_fail(tmp_path):
    with pytest.raises(FileNotFoundError, match="nodes.parquet"):
        load_data(tmp_path)


@pytest.mark.parametrize("table,column,value", [
    ("nodes", "gid", 1.5), ("nodes", "depth", 5), ("edges", "sum_kzt", -1),
    ("edges", "n_tx", 0), ("transactions", "sum_kzt", 0),
    ("transactions", "sum_kzt", np.inf), ("transactions", "date", "broken"),
    ("nodes", "is_seed", "maybe"), ("transactions", "src", 999999),
])
def test_invalid_inputs_rejected(sample_data, table, column, value):
    frames = {name: getattr(sample_data, name).copy() for name in ("edges", "nodes", "transactions")}
    frames[table][column] = frames[table][column].astype(object)
    frames[table].loc[0, column] = value
    with pytest.raises((ValueError, TypeError)):
        validate_data(**frames)


def test_duplicate_gid_rejected(sample_data):
    nodes = sample_data.nodes.copy()
    nodes.loc[1, "gid"] = nodes.loc[0, "gid"]
    with pytest.raises(ValueError, match="unique gid"):
        validate_data(sample_data.edges, nodes, sample_data.transactions)


def test_false_string_is_not_true(sample_data):
    nodes = sample_data.nodes.copy()
    nodes["is_seed"] = nodes.is_seed.map({True: "true", False: "false"})
    data = validate_data(sample_data.edges, nodes, sample_data.transactions)
    assert data.nodes.is_seed.sum() == sample_data.nodes.is_seed.sum()


def test_null_required_value_rejected(sample_data):
    tx = sample_data.transactions.copy()
    tx.loc[0, "sum_kzt"] = np.nan
    with pytest.raises(ValueError, match="null"):
        validate_data(sample_data.edges, sample_data.nodes, tx)


def test_amount_and_count_reconciliation(sample_data):
    edges = sample_data.edges.copy()
    edges.loc[0, "sum_kzt"] += 10
    with pytest.raises(ValueError, match="disagree"):
        validate_data(edges, sample_data.nodes, sample_data.transactions)
    edges = sample_data.edges.copy()
    edges.loc[0, "n_tx"] += 1
    with pytest.raises(ValueError, match="disagree"):
        validate_data(edges, sample_data.nodes, sample_data.transactions)
