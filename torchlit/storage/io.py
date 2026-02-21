from __future__ import annotations

import json
from pathlib import Path
from typing import Any

RUN_META_FILENAME = "meta.json"
METRICS_FILENAME = "metrics.jsonl"


def list_run_dirs(run_root: str = "runs") -> list[Path]:
    root = Path(run_root)
    if not root.exists():
        return []
    runs = [p for p in root.iterdir() if p.is_dir()]
    return sorted(runs, key=lambda p: p.stat().st_mtime, reverse=True)


def read_meta(run_dir: str | Path) -> dict[str, Any]:
    path = Path(run_dir) / RUN_META_FILENAME
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
        return data if isinstance(data, dict) else {}


def list_runs(run_root: str = "runs") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for run_dir in list_run_dirs(run_root):
        meta = read_meta(run_dir)
        created_ms = int(meta.get("created_ms", 0) or 0)
        out.append(
            {
                "run_id": str(meta.get("run_id", run_dir.name)),
                "path": str(run_dir),
                "created_ms": created_ms,
                "model_type": str(meta.get("model_type", "Unknown")),
                "name": str(meta.get("name", run_dir.name)),
            }
        )
    return out


def read_metrics_chunk(
    run_dir: str | Path,
    *,
    offset: int = 0,
    max_records: int = 5000,
) -> tuple[list[dict[str, Any]], int]:
    path = Path(run_dir) / METRICS_FILENAME
    if not path.exists():
        return [], 0

    records: list[dict[str, Any]] = []
    with path.open("rb") as f:
        f.seek(0, 2)
        file_size = f.tell()
        safe_offset = 0 if offset < 0 or offset > file_size else offset
        f.seek(safe_offset)

        while len(records) < max_records:
            line_start = f.tell()
            line = f.readline()
            if not line:
                break

            if not line.endswith(b"\n"):
                f.seek(line_start)
                break

            raw = line.decode("utf-8", errors="replace").strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if isinstance(obj, dict):
                records.append(obj)

        next_offset = f.tell()

    return records, next_offset
