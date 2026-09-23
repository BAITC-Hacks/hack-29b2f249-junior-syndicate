"""Local analyst workspace: search, graph, explanations and CSV downloads."""
from pathlib import Path
import os
import sys

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline import explain_node
from src.scoring import ROLES, amount_text
from src.workspace import load_workspace, ranked_nodes, graph_view, counterparties, network_figure

OUTPUT = Path(os.environ.get("MONEY_GRAPH_OUTPUT", str(ROOT / "output")))
st.set_page_config(page_title="Money Graph | Junior Syndicate", layout="wide")
st.title("Money Graph")
st.caption("Junior Syndicate · Анализ наблюдаемой сети переводов · Июль 2026")
try:
    nodes, edges, clusters, summary = load_workspace(OUTPUT)
except FileNotFoundError:
    st.info("Нет результатов анализа. Запустите python run.py из папки проекта.")
    st.stop()
except (ValueError, KeyError, pd.errors.ParserError) as error:
    st.error(f"Не удалось прочитать результаты: {error}. Повторите python run.py.")
    st.stop()

overview = st.columns(4)
for widget, label, value in zip(overview, ["Клиенты", "Связи", "Переводы", "Оборот, млн KZT"],
                                [f"{len(nodes):,}", f"{len(edges):,}", f"{summary['transactions']:,}", f"{summary['total_observed_kzt'] / 1_000_000:.2f}"]):
    widget.metric(label, value)
st.caption(f"Seed: {summary['seeds']} · Кластеры: {len(clusters)} · Компоненты со связями: {summary['components_with_edges']} · Изоляты: {summary['isolated_nodes']} · Расчёт: {summary['runtime_seconds']:.2f} с")
st.info("Роли — гипотезы для проверки. На depth=4 граф обрезан; входящие потоки неполны. Обоснованность роли не является вероятностью виновности.")

ranked = ranked_nodes(nodes)
st.sidebar.header("Найти клиента")
selected = st.sidebar.selectbox("Поиск GID", ranked.gid.astype(str).tolist(), key="gid")
gid = int(selected)
card = explain_node(gid, features=nodes)
metrics = card["metrics"]
mode = st.sidebar.selectbox("Режим карты", ["Окрестность GID", "Кластер", "Крупнейшая компонента", "Весь граф"], key="mode")
cluster_id = st.sidebar.selectbox("Кластер", sorted(clusters.cluster_id.tolist()), key="cluster")
color = st.sidebar.radio("Цвет узлов", ["Роль", "Кластер"], key="color")
st.sidebar.caption("Размер узла — приоритет. Стрелки показывают направление перевода. Наведите на узел или стрелку для деталей.")
if st.sidebar.button("Обновить результаты"):
    st.rerun()

network_tab, priority_tab, cluster_tab, quality_tab, resilience_tab = st.tabs(["Карта и клиент", "Кого проверить", "Сообщества", "Качество данных", "Стресс-тест"])
with network_tab:
    st.subheader(f"GID {gid}")
    st.write(card["evidence"])
    st.write(f"Кандидат на роль: **{card['role']}**")
    columns = st.columns(3)
    for widget, label, value in zip(columns, ["Обоснованность", "Приоритет", "Depth / кластер"],
                                    [f"{card['role_score']:.3f}", f"{card['priority_score']:.3f}", f"{metrics['depth']} / {card['cluster_id']}"]):
        widget.metric(label, value)
    visible_nodes, visible_edges = graph_view(nodes, edges, mode, gid, int(cluster_id))
    st.caption(f"Показано {len(visible_nodes)} узлов и {len(visible_edges)} связей")
    if gid not in set(visible_nodes.gid):
        st.caption("Выбранный клиент вне текущего среза карты. Режим «Окрестность GID» покажет его связи.")

    @st.cache_data(show_spinner="Строим карту сети…")
    def draw_network(visible_nodes: pd.DataFrame, visible_edges: pd.DataFrame, selected_gid: int, color_by: str):
        return network_figure(visible_nodes, visible_edges, selected_gid, color_by)

    st.plotly_chart(draw_network(visible_nodes, visible_edges, gid, "role" if color == "Роль" else "cluster_id"), width="stretch")
    left, right = st.columns(2)
    with left:
        st.markdown("**Денежный поток внутри выборки**")
        st.write(f"Вход: {metrics['sum_in']:,.0f} KZT · {int(metrics['n_in_tx'])} переводов")
        st.write(f"Выход: {metrics['sum_out']:,.0f} KZT · {int(metrics['n_out_tx'])} переводов")
        st.write(f"Плательщики: {metrics['in_degree']} · Получатели: {metrics['out_degree']}")
        st.caption(f"Наблюдаемая разность: {metrics['observed_net']:,.0f} KZT — это не баланс счёта.")
        st.write(f"FIFO-сопоставление ≤24ч: {metrics['forwarded_within_24h_ratio']:.0%}; ≤48ч: {metrics['forwarded_within_48h_ratio']:.0%}")
        st.caption("Эвристика по датам, не доказательство перевода тех же денег. Сопоставления в один день исключены.")
    with right:
        st.markdown("**Почему такой приоритет**")
        st.write(card["priority_why"])
        st.dataframe(pd.DataFrame(card["priority_factors"])[["label", "contribution"]], hide_index=True, width="stretch")
    with st.expander("Как рассчитана роль"):
        st.dataframe(pd.DataFrame(card["role_factors"])[["label", "contribution"]], hide_index=True, width="stretch")
        scores = pd.DataFrame({"role": ROLES, "score": [metrics[f"{role}_score"] for role in ROLES]})
        st.bar_chart(scores.set_index("role"))
        st.caption(f"Разница двух лучших scores: {metrics['role_margin']:.3f}; качество наблюдения: {metrics['observation_quality']:.2f}.")
    left, right = st.columns(2)
    for column, direction, title in ((left, "in", "От кого поступили"), (right, "out", "Кому отправлены")):
        with column:
            st.markdown(f"**{title}**")
            table = counterparties(edges, gid, direction).copy()
            table["gid"] = table.gid.astype(str)
            st.dataframe(table, hide_index=True, width="stretch")
    with st.expander("Ограничения и следующий запрос данных", expanded=bool(metrics["is_boundary_node"] or metrics["is_seed"])):
        for limitation in card["limitations"]:
            st.write("• " + limitation)
        st.write("Для проверки гипотезы запросите полные входящие/исходящие операции, точное время и продолжение за depth=4.")

with priority_tab:
    selected_role = st.selectbox("Роль в рейтинге", ["Все", *ROLES], key="rank_role")
    selected_cluster = st.selectbox("Кластер в рейтинге", ["Все", *[str(value) for value in sorted(clusters.cluster_id)]], key="rank_cluster")
    table = ranked_nodes(nodes, None if selected_role == "Все" else selected_role, None if selected_cluster == "Все" else int(selected_cluster))
    table = table[["gid", "role", "priority_score", "role_score", "cluster_id", "priority_why"]].head(100).copy()
    table["gid"] = table.gid.astype(str)
    st.caption("До 100 клиентов в выбранном срезе. Откройте GID через поиск слева.")
    st.dataframe(table, hide_index=True, width="stretch")
    for filename in ("nodes_roles.csv", "clusters.csv", "top_nodes.csv"):
        st.download_button(f"Скачать {filename}", (OUTPUT / filename).read_bytes(), file_name=filename, mime="text/csv")

with cluster_tab:
    group = clusters[clusters.cluster_id.eq(cluster_id)].iloc[0]
    st.subheader(f"Кластер {cluster_id}")
    st.write(group.hypothesis)
    st.write(f"Узлов: {group.n_nodes} · Seed: {group.n_seed} · Внутренний оборот: {group.sum_kzt_internal:,.0f} KZT")
    group_nodes, group_edges = graph_view(nodes, edges, "Кластер", gid, int(cluster_id))
    st.plotly_chart(draw_network(group_nodes, group_edges, gid, "role"), width="stretch", key="cluster_graph")
    table = ranked_nodes(nodes, cluster=int(cluster_id))[["gid", "role", "priority_score", "evidence"]].head(20).copy()
    table["gid"] = table.gid.astype(str)
    st.dataframe(table, hide_index=True, width="stretch")

with quality_tab:
    st.write(f"Граничные узлы без исходящих: {summary['boundary_sinks']}; среди них terminal: {summary['boundary_terminals']}.")
    st.write(f"Все компоненты, включая изоляты: {summary['components_including_isolates']}.")
    for warning in summary["warnings"]:
        st.warning(warning)
    distribution = pd.DataFrame.from_dict(summary["role_distribution"], orient="index", columns=["nodes"])
    st.bar_chart(distribution)
    st.json({"input_sha256": summary["input_sha256"], "betweenness": summary["betweenness"], "date_precision": summary["date_precision"]})

with resilience_tab:
    st.subheader("Как меняется связность при удалении узлов")
    st.caption("Сценарный расчёт на неориентированной проекции. Узлы по приоритету сравниваются с 30 случайными выборками. Это не рекомендация блокировки счетов.")
    resilience_path = OUTPUT / "resilience.csv"
    if resilience_path.exists():
        resilience = pd.read_csv(resilience_path)
        if resilience.empty:
            st.info("Недостаточно узлов для стресс-теста.")
        else:
            st.line_chart(resilience.pivot(index="removed_n", columns="strategy", values="largest_component_remaining_fraction"), x_label="Удалено узлов", y_label="Доля оставшихся узлов в крупнейшей компоненте")
            st.dataframe(resilience, hide_index=True, width="stretch")
    else:
        st.info("Обновите результаты командой python run.py.")
