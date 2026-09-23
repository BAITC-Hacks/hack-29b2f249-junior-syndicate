from pathlib import Path

import pandas as pd
import pytest

from src.load_data import validate_data
from src.graph_builder import build_graph, communities
from src.features import calculate_features
from src.scoring import load_config

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def config():
    return load_config(ROOT / "config/scoring.yaml")


@pytest.fixture
def sample_data():
    transfers = []
    for payer in range(1, 21):
        transfers.append((payer, 100, "2026-07-01", 100_000))
    for receiver in range(201, 281):
        transfers.append((200, receiver, "2026-07-05", 10_000))
    transfers.extend([
        (1, 300, "2026-07-01", 1_000_000), (300, 301, "2026-07-02", 950_000),
        (1, 400, "2026-07-01", 400_000), (1, 400, "2026-07-03", 400_000),
        (1, 500, "2026-07-01", 400_000), (1, 500, "2026-07-03", 400_000),
    ])
    tx = pd.DataFrame(transfers, columns=["src", "dst", "date", "sum_kzt"])
    ids = sorted({*tx.src, *tx.dst, 900})
    nodes = pd.DataFrame({"gid": ids})
    nodes["depth"] = [0 if gid <= 20 or gid == 900 else 4 if gid in range(201, 281) or gid == 500 else 1 for gid in ids]
    nodes["is_seed"] = nodes.depth.eq(0)
    edges = tx.groupby(["src", "dst"], as_index=False).agg(sum_kzt=("sum_kzt", "sum"), n_tx=("sum_kzt", "size"))
    edges["depth"] = 1
    return validate_data(edges, nodes, tx)


@pytest.fixture
def features(sample_data):
    graph = build_graph(sample_data.nodes, sample_data.edges)
    return calculate_features(sample_data.nodes, sample_data.edges, sample_data.transactions, graph, communities(graph))
