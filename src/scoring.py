"""Interpretable scores, explicit eligibility and auditable contributions."""
from __future__ import annotations

from pathlib import Path
import math
import numpy as np
import pandas as pd
import yaml

from .features import percentile_score

ROLES = ["consolidator", "transit", "distributor", "terminal", "coordinator", "peripheral"]
ROLE_COLORS = dict(zip(ROLES, ["#e76f51", "#3b82f6", "#f59e0b", "#22c55e", "#a855f7", "#94a3b8"]))
FACTOR_LABELS = {
    "fan_in": "Число плательщиков", "incoming_volume": "Входящий поток",
    "pagerank": "PageRank", "retention": "Наблюдаемое удержание",
    "upstream_diversity": "Разнообразие входящих сообществ",
    "fan_out": "Число получателей", "outgoing_volume": "Исходящий поток",
    "outgoing_count": "Исходящие переводы", "fan_out_ratio": "Доля исходящих связей",
    "flow_similarity": "Сходство входа и выхода", "forwarded_48h": "FIFO-сопоставление ≤48ч",
    "volume": "Наблюдаемый поток", "middle": "Входящие и исходящие связи",
    "betweenness": "Посредническая центральность", "incoming_count": "Входящие переводы",
    "bridge": "Связь сообществ", "seed_reach": "Достижимость от seed",
    "absence": "Недостаточно специализированных признаков",
    "structural": "Структурная значимость", "financial": "Объём потока",
    "seed_relevance": "Связь с seed", "role_importance": "Роль и её обоснованность",
    "anomaly": "Необычное число контрагентов", "temporal": "Временной паттерн",
}


def load_config(path: str | Path) -> dict:
    with Path(path).open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    if set(config["roles"]) != set(ROLES) - {"peripheral"}:
        raise ValueError("Configuration must define all five specialized roles")
    for name, weights in [*config["roles"].items(), ("priority", config["priority"])]:
        if any(not math.isfinite(w) or w < 0 for w in weights.values()) or not math.isclose(sum(weights.values()), 1, abs_tol=1e-8):
            raise ValueError(f"{name}: weights must be non-negative, finite and sum to 1")
    for name, value in config["thresholds"].items():
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"threshold {name} must be non-negative and finite")
    if config["thresholds"]["strong_degree"] < 1 or not 0 < config["thresholds"]["flow_tolerance"] < 1 or config["thresholds"]["confidence_margin_scale"] <= 0:
        raise ValueError("Degree and flow/margin scales must be positive")
    if config["top_n"] < 20 or config["betweenness_samples"] < 1 or config["community_resolution"] <= 0:
        raise ValueError("Invalid top_n, betweenness_samples or resolution")
    if set(config["role_importance"]) != set(ROLES) or any(not 0 <= w <= 1 for w in config["role_importance"].values()):
        raise ValueError("Role importance must contain all roles, with weights in [0,1]")
    for name in ("seed_flow_reliability", "boundary_quality", "seed_quality", "low_observation_quality", "terminal_fan_in_discount", "terminal_min_retention", "coordinator_betweenness_percentile"):
        if not 0 <= config["thresholds"][name] <= 1:
            raise ValueError(f"threshold {name} must be in [0,1]")
    return config


def assign_roles(frame: pd.DataFrame, config: dict) -> pd.DataFrame:
    result = frame.copy()
    thresholds = config["thresholds"]
    active = result.total_degree.gt(0)
    rank = lambda values: percentile_score(values.where(active, 0))
    reliability = pd.Series(np.where(result.is_seed, thresholds["seed_flow_reliability"], 1.0), index=result.index)
    retention = result.retention_ratio.fillna(0) * reliability
    fan_in = rank(result.in_degree) * (result.in_degree / thresholds["strong_degree"]).clip(upper=1)
    fan_out = rank(result.out_degree) * (result.out_degree / thresholds["strong_degree"]).clip(upper=1)
    flow_error = result.flow_through_ratio.sub(1).abs()
    similarity = (1 - (flow_error - thresholds["flow_tolerance"]).clip(lower=0) / (1 - thresholds["flow_tolerance"])).clip(0, 1).fillna(0)
    factors = {
        "fan_in": fan_in, "fan_out": fan_out, "incoming_volume": rank(result.sum_in),
        "outgoing_volume": rank(result.sum_out), "pagerank": rank(result.pagerank),
        "retention": retention, "upstream_diversity": rank(result.upstream_diversity),
        "outgoing_count": rank(result.n_out_tx), "fan_out_ratio": result.fan_out_ratio,
        "flow_similarity": similarity * reliability, "forwarded_48h": result.forwarded_within_48h_ratio,
        "volume": rank(result.sum_in + result.sum_out), "middle": (result.in_degree.gt(0) & result.out_degree.gt(0)).astype(float),
        "betweenness": rank(result.betweenness), "incoming_count": rank(result.n_in_tx),
        "bridge": (.7 * result.participation_coefficient + .3 * result.is_articulation.astype(float)).clip(0, 1),
        "seed_reach": rank(result.seed_reach),
    }
    eligible = {
        "consolidator": result.in_degree.ge(thresholds["min_specialized_degree"]) & result.sum_in.gt(0),
        "distributor": result.out_degree.ge(thresholds["min_specialized_degree"]) & result.sum_out.gt(0),
        "transit": result.in_degree.gt(0) & result.out_degree.gt(0) & result.sum_in.gt(0) & result.sum_out.gt(0) & (
            (~result.is_seed & result.flow_through_ratio.between(thresholds["transit_min_ratio"], thresholds["transit_max_ratio"]))
            | (result.is_seed & result.forwarded_within_48h_ratio.ge(thresholds["seed_transit_min_forwarding"]))
        ),
        "terminal": ~result.is_boundary_node & ~result.is_seed & result.in_degree.gt(0) & result.n_in_tx.ge(thresholds["terminal_min_transactions"]) & result.retention_ratio.ge(thresholds["terminal_min_retention"]),
        "coordinator": result.total_degree.ge(thresholds["coordinator_min_degree"]) & result.betweenness.gt(0) & factors["betweenness"].ge(thresholds["coordinator_betweenness_percentile"]) & (result.community_neighbors_count.ge(2) | result.is_articulation),
    }
    contributions = {}
    for role, weights in config["roles"].items():
        gate = eligible[role].astype(float)
        if role == "terminal":
            gate *= 1 - thresholds["terminal_fan_in_discount"] * fan_in
        result[f"{role}_eligible"] = eligible[role]
        for factor, weight in weights.items():
            if factor not in factors:
                raise ValueError(f"Unknown role factor {factor}")
            contributions[f"role_factor__{role}__{factor}"] = factors[factor] * weight * gate
    result = pd.concat([result, pd.DataFrame(contributions, index=result.index)], axis=1)
    for role in config["roles"]:
        result[f"{role}_score"] = result.filter(like=f"role_factor__{role}__").sum(axis=1)
    highest = result[[f"{role}_score" for role in config["roles"]]].max(axis=1)
    result["peripheral_score"] = 1 - highest
    result["role_factor__peripheral__absence"] = result.peripheral_score
    scores = result[[f"{role}_score" for role in ROLES]]
    ordered = np.sort(scores.to_numpy(), axis=1)
    result["role"] = scores.idxmax(axis=1).str.removesuffix("_score")
    result["role_margin"] = ordered[:, -1] - ordered[:, -2]
    quality = pd.Series(1.0, index=result.index)
    quality *= np.where(result.is_boundary_node, thresholds["boundary_quality"], 1)
    quality *= np.where(result.is_seed, thresholds["seed_quality"], 1)
    quality *= np.where((result.n_in_tx + result.n_out_tx) < 3, thresholds["low_observation_quality"], 1)
    result["observation_quality"] = quality
    result["role_score"] = ((.6 * ordered[:, -1] + .4 * (result.role_margin / thresholds["confidence_margin_scale"]).clip(upper=1)) * quality).clip(0, 1)
    result["secondary_role"] = scores.apply(lambda row: row.nlargest(2).index[-1].removesuffix("_score"), axis=1)
    return result


def assign_priority(frame: pd.DataFrame, config: dict) -> pd.DataFrame:
    result = frame.copy()
    active = result.total_degree.gt(0)
    rank = lambda values: percentile_score(values.where(active, 0))
    distance = result.minimum_distance_from_seed
    proximity = (1 / (1 + distance)).fillna(0)
    values = {
        "structural": (rank(result.betweenness) + rank(result.pagerank) + result.participation_coefficient) / 3,
        "financial": rank(result.sum_in + result.sum_out),
        "seed_relevance": .6 * rank(result.seed_reach) + .4 * proximity,
        "role_importance": result.role.map(config["role_importance"]) * result.role_score,
        "anomaly": (rank(result.in_degree) + rank(result.out_degree)) / 2,
        "temporal": result.forwarded_within_48h_ratio,
    }
    for name, value in values.items():
        result[f"priority_factor__{name}"] = config["priority"][name] * value * result.observation_quality * active
    result["priority_score"] = result.filter(like="priority_factor__").sum(axis=1)
    result["priority_why"] = result.apply(priority_explanation, axis=1)
    return result


def priority_explanation(row: pd.Series) -> str:
    columns = sorted([name for name in row.index if name.startswith("priority_factor__")], key=lambda name: -row[name])[:3]
    if row.priority_score == 0:
        return "Нет наблюдаемых связей: автоматический структурный приоритет равен 0; требуется расширить выгрузку."
    details = {
        "structural": f"betweenness={row.betweenness:.4f}, сообществ соседей={int(row.community_neighbors_count)}",
        "financial": f"вход={row.sum_in:,.0f}, выход={row.sum_out:,.0f} KZT",
        "seed_relevance": f"достижим от {int(row.seed_reach)} seed",
        "role_importance": f"кандидат {row.role}, обоснованность={row.role_score:.2f}",
        "anomaly": f"плательщиков={int(row.in_degree)}, получателей={int(row.out_degree)}",
        "temporal": f"FIFO ≤48ч={row.forwarded_within_48h_ratio:.0%}",
    }
    return "; ".join(f"{FACTOR_LABELS[name.split('__')[1]]}: +{row[name]:.3f} ({details[name.split('__')[1]]})" for name in columns)


def amount_text(amount: float) -> str:
    if abs(amount) >= 1_000_000_000:
        return f"{amount / 1_000_000_000:.2f} млрд"
    if abs(amount) >= 1_000_000:
        return f"{amount / 1_000_000:.2f} млн"
    return f"{amount:,.0f}".replace(",", " ")


def generate_evidence(row: pd.Series) -> str:
    limitations = []
    if row.is_boundary_node:
        limitations.append("depth=4: выход обрезан, terminal не подтверждён.")
    if row.is_seed:
        limitations.append("Seed: вход неполон.")
    suffix = " ".join(limitations)
    if row.role == "consolidator":
        text = f"Признаки консолидации: {int(row.in_degree)} плательщиков; вход {amount_text(row.sum_in)} KZT."
    elif row.role == "distributor":
        text = f"Признаки распределения: {int(row.out_degree)} получателей; выход {amount_text(row.sum_out)} KZT."
    elif row.role == "transit":
        text = f"Признаки транзита: вход {amount_text(row.sum_in)}, выход {amount_text(row.sum_out)} KZT; FIFO ≤48ч {row.forwarded_within_48h_ratio:.0%}."
    elif row.role == "terminal":
        text = f"Кандидат terminal: вход {amount_text(row.sum_in)} KZT; наблюдаемое удержание {row.retention_ratio:.0%}; depth={int(row.depth)}."
    elif row.role == "coordinator":
        text = f"Кандидат coordinator: betweenness={row.betweenness:.3g}; {int(row.community_neighbors_count)} сообществ соседей; достижим от {int(row.seed_reach)} seed."
    else:
        text = f"Недостаточно признаков роли; связей {int(row.total_degree)}, наблюдаемый поток {amount_text(row.sum_in + row.sum_out)} KZT."
    budget = 200 - len(suffix) - (1 if suffix else 0)
    if len(text) > budget:
        text = text[:budget - 1].rsplit(" ", 1)[0] + "…"
    return text + (" " + suffix if suffix else "")
