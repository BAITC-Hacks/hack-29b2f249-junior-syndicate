"""Reproducible batch analysis, quality gates, exports and node explanations."""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path
import time

import numpy as np
import pandas as pd

from .load_data import InputData, load_data
from .graph_builder import build_graph, communities
from .features import calculate_features
from .scoring import ROLES, FACTOR_LABELS, assign_roles, assign_priority, generate_evidence, load_config
from .resilience import assess_resilience, assess_ranking_stability

LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROLE_COLUMNS = ["gid", "role", "role_score", "cluster_id", "priority_score", "evidence"]
CLUSTER_COLUMNS = ["cluster_id", "n_nodes", "n_seed", "sum_kzt_internal", "top_gids", "hypothesis"]
TOP_COLUMNS = ["rank", "gid", "role", "priority_score", "why"]


def cluster_export(features: pd.DataFrame, edges: pd.DataFrame) -> pd.DataFrame:
    lookup = features.set_index("gid").cluster_id
    edge_clusters = edges.assign(src_cluster=edges.src.map(lookup), dst_cluster=edges.dst.map(lookup))
    internal = edge_clusters[edge_clusters.src_cluster == edge_clusters.dst_cluster].groupby("src_cluster").sum_kzt.sum()
    rows = []
    for cluster_id, group in features.groupby("cluster_id"):
        ranked = group.sort_values(["priority_score", "gid"], ascending=[False, True])
        roles = group.role.value_counts().to_dict()
        findings = [f"{role}: {roles[role]}" for role in ("consolidator", "distributor", "coordinator", "transit") if roles.get(role)]
        hypothesis = "Кандидаты — " + ", ".join(findings) if findings else "Выраженных центров не выявлено"
        hypothesis += f"; seed: {int(group.is_seed.sum())}; граничных узлов: {int(group.is_boundary_node.sum())}. Требуется проверка."
        rows.append({
            "cluster_id": int(cluster_id), "n_nodes": len(group), "n_seed": int(group.is_seed.sum()),
            "sum_kzt_internal": float(internal.get(cluster_id, 0)),
            "top_gids": ", ".join(map(str, ranked.gid.head(5))), "hypothesis": hypothesis,
        })
    return pd.DataFrame(rows, columns=CLUSTER_COLUMNS)


def validate_outputs(nodes: pd.DataFrame, roles: pd.DataFrame, clusters: pd.DataFrame, top: pd.DataFrame) -> None:
    if roles.columns.tolist() != ROLE_COLUMNS or clusters.columns.tolist() != CLUSTER_COLUMNS or top.columns.tolist() != TOP_COLUMNS:
        raise ValueError("Export schemas do not match case requirements")
    if len(roles) != len(nodes) or roles.gid.duplicated().any() or set(roles.gid) != set(nodes.gid):
        raise ValueError("Export does not contain every input node exactly once")
    if roles.isna().any().any() or not set(roles.role) <= set(ROLES):
        raise ValueError("Missing output fields or unknown role")
    for column in ("role_score", "priority_score"):
        if not np.isfinite(roles[column]).all() or not roles[column].between(0, 1).all():
            raise ValueError(f"Invalid {column}")
    if not roles.evidence.str.len().between(1, 200).all():
        raise ValueError("Evidence must contain 1..200 characters")
    if set(roles.cluster_id) != set(clusters.cluster_id) or clusters.cluster_id.duplicated().any():
        raise ValueError("Cluster IDs disagree")
    if clusters.n_nodes.sum() != len(nodes) or clusters.n_seed.sum() != nodes.is_seed.sum():
        raise ValueError("Cluster counts disagree")
    sizes = roles.groupby("cluster_id").size().sort_index()
    if not np.array_equal(sizes.to_numpy(), clusters.set_index("cluster_id").loc[sizes.index, "n_nodes"].to_numpy()):
        raise ValueError("Per-cluster node counts disagree")
    if len(top) < min(20, len(nodes)) or top.gid.duplicated().any() or top.isna().any().any():
        raise ValueError("Incomplete top list")
    if top["rank"].tolist() != list(range(1, len(top) + 1)) or not top.priority_score.is_monotonic_decreasing or top.why.str.strip().eq("").any():
        raise ValueError("Invalid ranking or priority explanation")
    expected = roles.sort_values(["priority_score", "gid"], ascending=[False, True]).head(len(top))
    if top.gid.tolist() != expected.gid.tolist():
        raise ValueError("Ranking differs from node scores")


def eda_report(data: InputData, features: pd.DataFrame) -> dict:
    columns = ["in_degree", "out_degree", "sum_in", "sum_out", "flow_through_ratio", "betweenness", "pagerank", "forwarded_within_24h_ratio", "forwarded_within_48h_ratio"]
    quantiles = features[columns].quantile([0, .25, .5, .9, .95, .99, 1])
    return {
        "tables": {name: {"shape": list(getattr(data, name).shape),
                          "dtypes": getattr(data, name).dtypes.astype(str).to_dict(),
                          "nulls": getattr(data, name).isna().sum().to_dict()}
                   for name in ("nodes", "edges", "transactions")},
        "depth_distribution": data.nodes.depth.value_counts().sort_index().to_dict(),
        "seed_distribution": data.nodes.groupby("depth").is_seed.sum().to_dict(),
        "component_sizes": features.groupby("weak_component_id").size().to_dict(),
        "feature_quantiles": json.loads(quantiles.to_json()),
        "transaction_amount_quantiles": json.loads(data.transactions.sum_kzt.quantile([0, .5, .9, .95, .99, 1]).to_json()),
    }


def run(data_dir: str | Path = PROJECT_ROOT / "data", output_dir: str | Path = PROJECT_ROOT / "output",
        config_path: str | Path = PROJECT_ROOT / "config/scoring.yaml", check_stability: bool = False) -> pd.DataFrame:
    started = time.perf_counter()
    data_dir, destination = Path(data_dir).resolve(), Path(output_dir).resolve()
    if destination == data_dir:
        raise ValueError("Output directory must differ from input directory")
    config = load_config(config_path)
    LOGGER.info("[1/8] Loading and reconciling parquet tables")
    data = load_data(data_dir)
    LOGGER.info("[2/8] Building graph including isolates")
    graph = build_graph(data.nodes, data.edges)
    LOGGER.info("[3/8] Deterministic Louvain communities")
    cluster_map = communities(graph, config["random_seed"], config["community_resolution"])
    LOGGER.info("[4/8] Computing features and EDA")
    features = calculate_features(data.nodes, data.edges, data.transactions, graph, cluster_map,
                                  config["betweenness_samples"], config["betweenness_exact_limit"], config["random_seed"])
    eda = eda_report(data, features)
    LOGGER.info("[5/8] Explainable role scores and eligibility")
    scored = assign_roles(features, config)
    LOGGER.info("[6/8] Priority contributions and evidence")
    scored = assign_priority(scored, config)
    scored["evidence"] = scored.apply(generate_evidence, axis=1)
    ranked = scored.sort_values(["priority_score", "gid"], ascending=[False, True])
    roles = ranked[ROLE_COLUMNS].reset_index(drop=True)
    clusters = cluster_export(scored, data.edges)
    top = ranked.head(config["top_n"])[["gid", "role", "priority_score", "priority_why"]].rename(columns={"priority_why": "why"}).reset_index(drop=True)
    top.insert(0, "rank", range(1, len(top) + 1))
    validate_outputs(data.nodes, roles, clusters, top)
    warnings = list(data.warnings)
    if scored.role.value_counts(normalize=True).max() >= .7:
        warnings.append("One role covers >=70% of nodes. Inspect evidence; no role quotas are imposed.")
    if len(nodes_without_activity := scored[scored.total_degree.eq(0)]):
        LOGGER.info("Isolated nodes retained: %s", len(nodes_without_activity))
    if (scored.is_boundary_node & scored.role.eq("terminal")).any():
        raise ValueError("Boundary node classified terminal")
    LOGGER.info("[7/8] Writing exports and audit reports")
    destination.mkdir(parents=True, exist_ok=True)
    for name, table in (("nodes_roles", roles), ("clusters", clusters), ("top_nodes", top),
                        ("node_features", scored), ("graph_edges", data.edges)):
        table.to_csv(destination / f"{name}.csv", index=False, encoding="utf-8-sig")
    assess_resilience(graph, ranked.gid.tolist(), config["random_seed"]).to_csv(destination / "resilience.csv", index=False)
    if check_stability:
        LOGGER.info("Checking top-20 sensitivity: priority weights and community resolution separately")
        stability_scenarios, stability_nodes = assess_ranking_stability(data, graph, features, config)
        stability_scenarios.to_csv(destination / "ranking_stability_scenarios.csv", index=False, encoding="utf-8-sig")
        stability_nodes.to_csv(destination / "ranking_stability_nodes.csv", index=False, encoding="utf-8-sig")
    summary = {
        "input_directory": str(data_dir), "source": "provided parquet",
        "nodes": len(data.nodes), "edges": len(data.edges), "transactions": len(data.transactions),
        "seeds": int(data.nodes.is_seed.sum()), "total_observed_kzt": float(data.edges.sum_kzt.sum()),
        "clusters": len(clusters), "components_including_isolates": int(scored.weak_component_id.nunique()),
        "components_with_edges": int(scored.loc[scored.total_degree.gt(0), "weak_component_id"].nunique()),
        "isolated_nodes": int(scored.total_degree.eq(0).sum()),
        "role_distribution": {role: int(scored.role.eq(role).sum()) for role in ROLES},
        "boundary_sinks": int((scored.is_boundary_node & scored.out_degree.eq(0)).sum()),
        "boundary_terminals": int((scored.is_boundary_node & scored.role.eq("terminal")).sum()),
        "terminal_candidates_inside_boundary": int((~scored.is_boundary_node & scored.role.eq("terminal")).sum()),
        "observed_ratio_08_12_nonseed": int((~scored.is_seed & scored.flow_through_ratio.between(.8, 1.2)).sum()),
        "date_precision": "date-only" if data.transactions.date.eq(data.transactions.date.dt.normalize()).all() else "timestamp",
        "betweenness": {"mode": "sampled" if len(graph) > config["betweenness_exact_limit"] else "exact",
                        "samples": min(len(graph), config["betweenness_samples"])},
        "warnings": warnings, "config": config,
        "input_sha256": {name: hashlib.sha256((data_dir / f"{name}.parquet").read_bytes()).hexdigest() for name in ("nodes", "edges", "transactions")},
        "runtime_seconds": round(time.perf_counter() - started, 3),
    }
    if check_stability:
        summary["ranking_stability"] = {"top_n": int(stability_scenarios.top_n.iloc[0]),
                                        "perturbations": len(stability_scenarios) - 1,
                                        "priority_weight_multipliers": [.9, 1.1],
                                        "community_resolution_multipliers": [.8, 1.2]}
    for name, report in (("run_summary", summary), ("eda_report", eda)):
        (destination / f"{name}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=int, allow_nan=False), encoding="utf-8")
    report_lines = ["# Результаты Qadam", "",
                    f"Узлы: {len(scored)}; рёбра: {len(data.edges)}; транзакции: {len(data.transactions)}.",
                    f"Наблюдаемый оборот: {summary['total_observed_kzt']:,.2f} KZT; время: {summary['runtime_seconds']:.3f} с.", "",
                    "## Роли", "", "| Роль | Узлов |", "|---|---:|"]
    report_lines.extend(f"| {role} | {count} |" for role, count in summary["role_distribution"].items())
    report_lines.extend(["", f"Кластеров: {len(clusters)}; с ≥2 seed: {int(clusters.n_seed.ge(2).sum())}.",
                         f"Компонент со связями: {summary['components_with_edges']}; вместе с изолятами: {summary['components_including_isolates']}.",
                         f"Граничных стоков: {summary['boundary_sinks']}; классифицированы terminal: {summary['boundary_terminals']}.",
                         f"Кандидатов terminal при depth<4: {summary['terminal_candidates_inside_boundary']}.", "",
                         "## Top 20", "", "| Место | GID | Роль | Приоритет |", "|---:|---|---|---:|"])
    report_lines.extend(f"| {row.rank} | {row.gid} | {row.role} | {row.priority_score:.4f} |" for row in top.head(20).itertuples())
    report_lines.extend(["", "## Почему первые пять", ""])
    report_lines.extend(f"- {row.gid}: {row.why}" for row in top.head(5).itertuples())
    report_lines.extend(["", "## Примеры для демонстрации", ""])
    for role in ROLES:
        candidates = ranked[ranked.role.eq(role)]
        if not candidates.empty:
            row = candidates.iloc[0]
            report_lines.append(f"- {role}: GID {row.gid}. {row.evidence}")
    report_lines.extend(["", "## Ограничения", "",
                         "Нет ground truth: оценки не являются точностью классификатора или вероятностью виновности.",
                         "Граница depth=4 скрывает выход; входы неполны, особенно у seed; переводы <5 000 KZT и другие банки отсутствуют.",
                         "Даты имеют точность до дня. FIFO не доказывает происхождение средств, не сопоставляет события в один день и не расходует один платёж дважды.", ""])
    report_lines.extend(f"- {warning}" for warning in warnings)
    (destination / "analysis_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    if check_stability:
        lines = ["# Qadam: устойчивость топ-20", "",
                 "Проверка чувствительности к настройкам, не оценка точности и не вероятность виновности.",
                 "Основной рейтинг не меняется. Базовый сценарий исключён из частот и диапазонов мест.",
                 "Каждый вес priority меняется отдельно на ±10%, затем все веса делятся на их новую сумму.",
                 "Отдельно resolution умножается на 0.8 и 1.2; заново рассчитываются сообщества, признаки, роли и приоритет.",
                 "Random seed и остальные параметры фиксированы. Не проверяются совместные изменения весов, пороги ролей и полнота данных.",
                 "При равных score порядок определяется GID по возрастанию, а не аналитическим отличием узлов.",
                 "Частота попадания относится только к указанным сценариям и не является вероятностью.", "",
                 "## Сценарии", "", "| Сценарий | Совпало с базовым топом | Макс. сдвиг базового топа | Кластеров | Изменений роли | Равенство на границе топа |",
                 "|---|---:|---:|---:|---:|---|"]
        lines.extend(f"| {row.scenario} | {row.overlap_count}/{row.top_n} | {row.max_abs_rank_shift_base_top} | {row.n_clusters} | {row.role_changes} | {'да' if row.cutoff_tie_crosses_top_n else 'нет'} |"
                     for row in stability_scenarios.itertuples())
        for kind, title in (("priority_weights", "Веса приоритета"), ("community_resolution", "Кластеризация")):
            group = stability_nodes[stability_nodes.kind.eq(kind) & stability_nodes.in_baseline_top]
            kept = int(group.top_n_hits.eq(group.scenario_count).sum())
            LOGGER.info("Stability %s: %s/%s baseline top nodes retained in every scenario", kind, kept, len(group))
            lines.extend(["", f"## {title}", "", f"Остались в топе во всех сценариях этой группы: {kept}/{len(group)}.", "",
                          "| GID | Базовое место | Попаданий в топ / сценариев | Лучшее место | Худшее место | Изменений роли |",
                          "|---|---:|---:|---:|---:|---:|"])
            lines.extend(f"| {row.gid} | {row.baseline_rank} | {row.top_n_hits}/{row.scenario_count} | {row.best_rank} | {row.worst_rank} | {row.role_change_count} |"
                         for row in group.itertuples())
        lines.extend(["", "## Воспроизводимость", "", "Полные результаты всех узлов: ranking_stability_nodes.csv; параметры и состав изменений: ranking_stability_scenarios.csv.",
                      "Конфигурация базового расчёта:", "", "```json", json.dumps(config, ensure_ascii=False, indent=2), "```", "",
                      "SHA256 входных Parquet:", ""])
        lines.extend(f"- {name}: {digest}" for name, digest in summary["input_sha256"].items())
        lines.extend(["", "Ограничения: depth=4 обрезает выход; входы seed неполны; другие банки и переводы ниже порога не наблюдаются. Размеченных ролей нет."])
        (destination / "ranking_stability_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    LOGGER.info("[8/8] Pipeline completed: %.3f seconds", summary["runtime_seconds"])
    LOGGER.info("Roles: %s", summary["role_distribution"])
    LOGGER.info("Clusters=%s; components=%s (including isolates); boundary terminals=%s", summary["clusters"], summary["components_including_isolates"], summary["boundary_terminals"])
    LOGGER.info("Top 10:\n%s", top.head(10)[["rank", "gid", "role", "priority_score"]].to_string(index=False))
    return scored


def explain_node(gid: int, output_dir: str | Path = PROJECT_ROOT / "output", features: pd.DataFrame | None = None) -> dict:
    data = features if features is not None else pd.read_csv(Path(output_dir) / "node_features.csv")
    matches = data[data.gid.eq(gid)]
    if matches.empty:
        raise KeyError(f"GID {gid} отсутствует в выгрузке")
    record = matches.iloc[0]
    metrics = {name: (None if pd.isna(value) else value.item() if hasattr(value, "item") else value)
               for name, value in record.items() if not name.startswith(("role_factor__", "priority_factor__"))}
    role_prefix = f"role_factor__{record.role}__"
    def factors(prefix: str) -> list[dict]:
        return sorted([{"factor": name.removeprefix(prefix), "label": FACTOR_LABELS.get(name.removeprefix(prefix), name),
                        "contribution": float(record[name])}
                       for name in record.index if name.startswith(prefix)], key=lambda item: -item["contribution"])
    limitations = ["Показаны только внутрибанковские переводы ≥5 000 KZT за июль 2026; полный баланс неизвестен.",
                   "Роль — проверяемая гипотеза; role_score не является вероятностью виновности.",
                   "FIFO сопоставляет суммы по времени и не доказывает происхождение средств; порядок внутри дня неизвестен."]
    if record.is_boundary_node:
        limitations.append("depth=4: исходящие операции за границей обхода не наблюдаются.")
    if record.is_seed:
        limitations.append("Seed: входящий поток неполон; коэффициент out/in ненадёжен.")
    if record.total_degree == 0:
        limitations.append("Узел сохранён из nodes, хотя его нет в рёбрах. Нужна дополнительная выгрузка.")
    return {"gid": int(gid), "role": record.role, "role_score": float(record.role_score),
            "priority_score": float(record.priority_score), "cluster_id": int(record.cluster_id),
            "evidence": record.evidence, "priority_why": record.priority_why, "metrics": metrics,
            "role_factors": factors(role_prefix), "priority_factors": factors("priority_factor__"),
            "limitations": limitations}


def main() -> None:
    parser = argparse.ArgumentParser(description="Qadam: parquet -> roles, clusters, priority")
    parser.add_argument("--data", type=Path, default=PROJECT_ROOT / "data")
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "output")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config/scoring.yaml")
    parser.add_argument("--check-stability", action="store_true", help="Additionally audit top-20 sensitivity without changing the baseline ranking")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        run(args.data, args.out, args.config, check_stability=args.check_stability)
    except (ValueError, FileNotFoundError) as error:
        parser.exit(1, f"Pipeline failed: {error}\n")


if __name__ == "__main__":
    main()
