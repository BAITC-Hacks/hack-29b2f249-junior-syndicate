"""Strict validation of the three input tables, including reconciliation."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import logging

import numpy as np
import pandas as pd

LOGGER = logging.getLogger(__name__)
REQUIRED = {
    "edges": ["src", "dst", "sum_kzt", "n_tx", "depth"],
    "nodes": ["gid", "depth", "is_seed"],
    "transactions": ["src", "dst", "date", "sum_kzt"],
}


@dataclass(frozen=True)
class InputData:
    edges: pd.DataFrame
    nodes: pd.DataFrame
    transactions: pd.DataFrame
    warnings: list[str] = field(default_factory=list)


def validate_data(edges: pd.DataFrame, nodes: pd.DataFrame, transactions: pd.DataFrame) -> InputData:
    tables = {"edges": edges.copy(), "nodes": nodes.copy(), "transactions": transactions.copy()}
    warnings: list[str] = []
    for name, frame in tables.items():
        missing = set(REQUIRED[name]) - set(frame.columns)
        if missing:
            raise ValueError(f"{name}: missing required columns {sorted(missing)}")
        if frame[REQUIRED[name]].isna().any().any():
            raise ValueError(f"{name}: null values in required fields")
        for column in ("gid", "src", "dst", "depth", "n_tx", "sum_kzt"):
            if column not in frame:
                continue
            values = pd.to_numeric(frame[column], errors="raise")
            if not np.isfinite(values).all():
                raise ValueError(f"{name}.{column}: non-finite values")
            if column != "sum_kzt":
                if (values % 1 != 0).any() or (values < 0).any():
                    raise ValueError(f"{name}.{column}: expected non-negative integers")
                if (values > np.iinfo(np.int64).max).any():
                    raise ValueError(f"{name}.{column}: exceeds int64")
                values = values.astype("int64")
            if column in ("n_tx", "sum_kzt") and (values <= 0).any():
                raise ValueError(f"{name}.{column}: must be positive (zero values are not silently discarded)")
            if column == "depth" and (values > 4).any():
                raise ValueError(f"{name}.depth: expected 0..4 for this case")
            frame[column] = values
    edges, nodes, transactions = (tables[name] for name in REQUIRED)
    if nodes.empty or nodes.gid.duplicated().any():
        raise ValueError("nodes: expected non-empty table with unique gid")
    boolean_values = nodes.is_seed.astype(str).str.lower().map({"true": True, "false": False, "1": True, "0": False})
    if boolean_values.isna().any():
        raise ValueError("nodes.is_seed: expected boolean, 0/1 or true/false")
    nodes["is_seed"] = boolean_values.astype(bool)
    if (nodes.is_seed & nodes.depth.ne(0)).any():
        raise ValueError("Seed nodes must have depth=0")
    known = set(nodes.gid)
    for name, frame in (("edges", edges), ("transactions", transactions)):
        if (set(frame.src) | set(frame.dst)) - known:
            raise ValueError(f"{name}: endpoint absent from nodes")
    try:
        transactions["date"] = pd.to_datetime(transactions.date, errors="raise", format="mixed", utc=True)
    except (ValueError, TypeError) as error:
        raise ValueError("transactions.date: invalid timestamp") from error
    if transactions.date.isna().any():
        raise ValueError("transactions.date: invalid timestamp")
    if edges.duplicated(["src", "dst"]).any():
        warnings.append("Duplicate edges aggregated by src/dst; sum amounts/counts, minimum depth.")
    edges = edges.groupby(["src", "dst"], as_index=False, sort=True).agg(
        sum_kzt=("sum_kzt", "sum"), n_tx=("n_tx", "sum"), depth=("depth", "min")
    )
    totals = transactions.groupby(["src", "dst"]).agg(sum_kzt=("sum_kzt", "sum"), n_tx=("sum_kzt", "size"))
    comparison = edges.set_index(["src", "dst"])[["sum_kzt", "n_tx"]].join(totals, how="outer", rsuffix="_tx")
    if comparison.isna().any().any() or not np.allclose(comparison.sum_kzt, comparison.sum_kzt_tx, atol=.01, rtol=1e-10) or not comparison.n_tx.eq(comparison.n_tx_tx).all():
        raise ValueError("edges and transactions disagree on pairs, amounts or transaction counts")
    if transactions.duplicated().any():
        warnings.append("Identical transaction rows retained: without a transaction ID duplicates cannot be established.")
    if (transactions.sum_kzt < 5000).any():
        warnings.append("Transactions below 5,000 KZT: dataset differs from the case threshold.")
    if ((transactions.date.dt.year != 2026) | (transactions.date.dt.month != 7)).any():
        warnings.append("Transaction dates outside July 2026.")
    if not transactions.empty and transactions.date.eq(transactions.date.dt.normalize()).all():
        warnings.append("Date-only timestamps: intraday ordering is unknown; same-timestamp forwarding is excluded.")
    if edges.src.eq(edges.dst).any():
        warnings.append("Self transfers retained in totals; excluded from counterparties and temporal matching.")
    isolated = known - (set(edges.src) | set(edges.dst))
    if isolated:
        warnings.append(f"{len(isolated)} nodes have no edges; all retained, including seeds.")
    for warning in warnings:
        LOGGER.warning(warning)
    return InputData(edges, nodes.sort_values("gid").reset_index(drop=True), transactions.sort_values(["date", "src", "dst"]).reset_index(drop=True), warnings)


def load_data(data_dir: str | Path) -> InputData:
    directory = Path(data_dir)
    paths = {name: directory / f"{name}.parquet" for name in REQUIRED}
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing input files: " + ", ".join(missing))
    return validate_data(**{name: pd.read_parquet(path) for name, path in paths.items()})
