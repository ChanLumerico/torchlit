import os
import json
import time
import uuid

from dataclasses import dataclass
from types import TracebackType
from typing import Any, Iterable, Iterator, Mapping

import torch
import torch.nn as nn


def _now_ms() -> int:
    return int(time.time() * 1000)


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _safe_float(x: Any) -> float | None:
    try:
        if isinstance(x, (int, float)):
            return float(x)
        if isinstance(x, torch.Tensor):
            return float(x.detach().item())
        return float(x)
    except Exception:
        return None


def _grad_global_norm(model: nn.Module) -> float | None:
    total = 0.0
    has_any = False
    for p in model.parameters():
        if p.grad is None:
            continue

        g = p.grad.detach()
        if g.is_sparse:
            g = g.coalesce().values()

        total += float(g.float().pow(2).sum().item())
        has_any = True

    return (total**0.5) if has_any else None


@dataclass
class TrainTrackerConfig:
    flush_every: int = 1
    flush_seconds: float = 1.0
    compute_grad_norm: bool = False
    include_lr: bool = True
    include_gpu_mem: bool = True


class TrainTracker:
    def __init__(
        self,
        model: nn.Module,
        optimizer: torch.optim.Optimizer | None = None,
        run_root: str = "runs",
        name: str = "train",
        config: TrainTrackerConfig | None = None,
        extra_meta: dict[str, Any] | None = None,
    ) -> None:
        self.model = model
        self.optimizer = optimizer
        self.run_root = run_root
        self.name = name
        self.cfg = config or TrainTrackerConfig()
        self.extra_meta = extra_meta or {}

        self.run_id = f"{name}-{_now_ms()}-{uuid.uuid4().hex[:8]}"
        self.run_dir = os.path.join(run_root, self.run_id)
        self.metrics_path = os.path.join(self.run_dir, "metrics.jsonl")
        self.meta_path = os.path.join(self.run_dir, "meta.json")

        self._fh: Any | None = None
        self._buffered = 0
        self._start_ms: int | None = None
        self._last_step_ms: int | None = None
        self._last_flush_monotonic = 0.0

    def __enter__(self) -> TrainTracker:
        _ensure_dir(self.run_dir)
        self._start_ms = _now_ms()
        self._last_step_ms = self._start_ms
        self._last_flush_monotonic = time.monotonic()

        meta = {
            "schema_version": "1.0",
            "run_id": self.run_id,
            "name": self.name,
            "created_ms": self._start_ms,
            "model_type": type(self.model).__name__,
            "device": self._infer_device(),
            "tracker": {
                "flush_every": int(self.cfg.flush_every),
                "flush_seconds": float(self.cfg.flush_seconds),
                "compute_grad_norm": bool(self.cfg.compute_grad_norm),
                "include_lr": bool(self.cfg.include_lr),
                "include_gpu_mem": bool(self.cfg.include_gpu_mem),
            },
            "extra": self.extra_meta,
        }
        with open(self.meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        self._fh = open(self.metrics_path, "a", encoding="utf-8")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        del tb
        self._update_meta(
            ended_ms=_now_ms(),
            ok=exc_type is None,
            error=None if exc is None else str(exc),
        )
        if self._fh:
            try:
                self._fh.flush()
                os.fsync(self._fh.fileno())
            except Exception:
                pass
            try:
                self._fh.close()
            except Exception:
                pass

        self._fh = None

    def step_end(
        self,
        *,
        step: int,
        metrics: Mapping[str, Any],
        epoch: int | None = None,
        split: str = "train",
    ) -> None:
        if self._fh is None:
            raise RuntimeError("TrainTracker must be used as a context manager.")

        now = _now_ms()
        dt_ms = now - (self._last_step_ms or now)
        self._last_step_ms = now

        record: dict[str, Any] = {
            "t_ms": now,
            "step": int(step),
            "epoch": int(epoch) if epoch is not None else None,
            "split": split,
            "dt_ms": int(dt_ms),
        }

        for k, v in metrics.items():
            fv = _safe_float(v)
            if fv is not None:
                record[k] = fv

        if self.cfg.include_lr and self.optimizer is not None:
            record["lr"] = self._get_lr(self.optimizer)

        if self.cfg.include_gpu_mem:
            record["gpu_mem_mb"] = self._get_gpu_mem_mb()

        if self.cfg.compute_grad_norm:
            record["grad_norm"] = _grad_global_norm(self.model)

        self._write_event(record)

    def log(self, *, step: int, key: str, value: Any, split: str = "train") -> None:
        self.step_end(step=step, metrics={key: value}, split=split)

    def iter(self, loader: Iterable[Any]) -> Iterable[Any]:
        for batch in loader:
            yield batch

    def _write_event(self, obj: dict[str, Any]) -> None:
        if self._fh is None:
            return

        self._fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self._buffered += 1

        due_to_count = self._buffered >= max(1, int(self.cfg.flush_every))
        due_to_time = (time.monotonic() - self._last_flush_monotonic) >= float(
            self.cfg.flush_seconds
        )
        if due_to_count or due_to_time:
            self._buffered = 0
            self._last_flush_monotonic = time.monotonic()
            self._fh.flush()
            try:
                os.fsync(self._fh.fileno())
            except Exception:
                pass

    def _infer_device(self) -> str:
        return str(self._model_device())

    def _get_lr(self, opt: torch.optim.Optimizer) -> float | None:
        try:
            return float(opt.param_groups[0].get("lr", None))
        except Exception:
            return None

    def _get_gpu_mem_mb(self) -> float | None:
        try:
            device = self._model_device()

            if device.type == "cuda":
                if not torch.cuda.is_available():
                    return None
                device_index = device.index
                if device_index is None:
                    device_index = torch.cuda.current_device()
                return float(
                    torch.cuda.memory_allocated(device_index) / (1024.0 * 1024.0)
                )

            if device.type == "mps":
                backends_mps = getattr(getattr(torch, "backends", None), "mps", None)
                if backends_mps is None:
                    return None
                is_available = getattr(backends_mps, "is_available", None)
                if callable(is_available) and not is_available():
                    return None

                mps_mod = getattr(torch, "mps", None)
                if mps_mod is None:
                    return None

                current_allocated = getattr(mps_mod, "current_allocated_memory", None)
                if callable(current_allocated):
                    return float(current_allocated() / (1024.0 * 1024.0))

                driver_allocated = getattr(mps_mod, "driver_allocated_memory", None)
                if callable(driver_allocated):
                    return float(driver_allocated() / (1024.0 * 1024.0))

                return None

            return None
        except Exception:
            return None

    def _model_device(self) -> torch.device:
        try:
            return next(self.model.parameters()).device
        except StopIteration:
            return torch.device("cpu")

    def _update_meta(self, **updates: Any) -> None:
        try:
            current: dict[str, Any] = {}
            if os.path.exists(self.meta_path):
                with open(self.meta_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        current = loaded
            current.update(updates)
            with open(self.meta_path, "w", encoding="utf-8") as f:
                json.dump(current, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
