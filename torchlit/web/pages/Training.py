from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

from torchlit.storage.io import list_runs, read_meta, read_metrics_chunk

RESERVED_KEYS = {"t_ms", "step", "epoch", "split", "dt_ms"}


def _format_created_ms(created_ms: int) -> str:
    if created_ms <= 0:
        return "-"
    return datetime.fromtimestamp(created_ms / 1000.0).strftime("%Y-%m-%d %H:%M:%S")


def _extract_metric_keys(rows: list[dict[str, Any]]) -> list[str]:
    keys: set[str] = set()
    for row in rows:
        for key, value in row.items():
            if key in RESERVED_KEYS:
                continue
            if isinstance(value, (int, float)):
                keys.add(key)
    return sorted(keys)


def _prepare_line_chart_data(
    rows: list[dict[str, Any]],
    metric_keys: list[str],
) -> list[dict[str, float | int | str]]:
    long_rows: list[dict[str, float | int | str]] = []
    for row in rows:
        if "step" not in row:
            continue
        step = int(row["step"])
        for key in metric_keys:
            value = row.get(key)
            if isinstance(value, (int, float)):
                long_rows.append({"step": step, "metric": key, "value": float(value)})
    return long_rows


def render() -> None:
    st.title("Training Metrics")
    st.caption("Append-only JSONL metrics viewer for TrainTracker runs")

    run_root = st.sidebar.text_input("Run root", value=st.session_state.get("run_root", "runs"))
    st.session_state["run_root"] = run_root

    runs = list_runs(run_root)
    if not runs:
        st.info(f"No runs found under `{run_root}`")
        return

    labels = [
        f"{run['run_id']}  |  {run['model_type']}  |  {_format_created_ms(int(run['created_ms']))}"
        for run in runs
    ]
    selected_index = st.sidebar.selectbox(
        "Run",
        options=range(len(runs)),
        index=0,
        format_func=lambda i: labels[i],
    )

    selected = runs[int(selected_index)]
    run_dir = selected["path"]
    run_key = str(Path(run_dir).resolve())

    auto_refresh = st.sidebar.checkbox("Auto refresh", value=True)
    refresh_seconds = st.sidebar.slider("Refresh (sec)", min_value=1, max_value=10, value=2)
    max_points = st.sidebar.slider("Max points", min_value=200, max_value=20000, value=4000, step=200)

    prev_key = st.session_state.get("training_selected_run_key")
    if prev_key != run_key:
        st.session_state["training_offset"] = 0
        st.session_state["training_rows"] = []
        st.session_state["training_selected_run_key"] = run_key

    offset = int(st.session_state.get("training_offset", 0))
    rows_cache = list(st.session_state.get("training_rows", []))
    new_rows, next_offset = read_metrics_chunk(run_dir, offset=offset, max_records=5000)

    if new_rows:
        rows_cache.extend(new_rows)
        if len(rows_cache) > max_points:
            rows_cache = rows_cache[-max_points:]
        st.session_state["training_rows"] = rows_cache
    st.session_state["training_offset"] = next_offset

    meta = read_meta(run_dir)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Run ID", str(meta.get("run_id", selected["run_id"])))
    c2.metric("Model", str(meta.get("model_type", "Unknown")))
    c3.metric("Device", str(meta.get("device", "Unknown")))
    c4.metric("Rows", str(len(rows_cache)))

    if not rows_cache:
        st.warning("No metrics yet. Keep training and this view will update.")
    else:
        all_metric_keys = _extract_metric_keys(rows_cache)
        default_metrics = [k for k in ["loss", "lr", "gpu_mem_mb", "grad_norm"] if k in all_metric_keys]
        if not default_metrics:
            default_metrics = all_metric_keys[: min(3, len(all_metric_keys))]

        selected_metrics = st.multiselect(
            "Metrics",
            options=all_metric_keys,
            default=default_metrics,
        )

        chart_rows = _prepare_line_chart_data(rows_cache, selected_metrics)
        if chart_rows:
            st.line_chart(chart_rows, x="step", y="value", color="metric")
        else:
            st.info("Select at least one numeric metric to plot.")

        with st.expander("Recent raw rows", expanded=False):
            st.json(rows_cache[-20:])

    st.caption(f"Run path: `{run_dir}`")

    if st.button("Refresh now"):
        st.rerun()

    if auto_refresh:
        time.sleep(refresh_seconds)
        st.rerun()
