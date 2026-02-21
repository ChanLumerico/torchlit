import os
import json
import sys
import time
import urllib.error
import urllib.request
import uuid

from dataclasses import dataclass
from pathlib import Path
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
    auto_launch_web: bool = True
    web_host: str = "127.0.0.1"
    web_port: int = 8501
    web_open_browser: bool = True
    web_once_per_process: bool = True
    web_wait_ready: bool = True
    web_ready_timeout_sec: float = 20.0
    web_ready_poll_interval_sec: float = 0.25
    enable_tqdm: bool = True
    tqdm_leave: bool = False
    tqdm_dynamic_ncols: bool = True
    tqdm_mininterval: float = 0.1


class TrainTracker:
    _launched_web_roots: set[str] = set()

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
        self._web_url: str | None = None
        self._web_ready = False
        self._pbar: Any | None = None
        self._pbar_last_split: str | None = None
        self._pbar_last_epoch: int | None = None
        self._pbar_last_step: int | None = None
        self._tqdm_checked = False
        self._tqdm_cls: Any | None = None

    def __enter__(self) -> TrainTracker:
        _ensure_dir(self.run_dir)
        self._start_ms = _now_ms()
        self._last_step_ms = self._start_ms
        self._last_flush_monotonic = time.monotonic()
        self._maybe_launch_web()

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
                "auto_launch_web": bool(self.cfg.auto_launch_web),
                "web_host": str(self.cfg.web_host),
                "web_port": int(self.cfg.web_port),
                "web_wait_ready": bool(self.cfg.web_wait_ready),
                "web_ready_timeout_sec": float(self.cfg.web_ready_timeout_sec),
                "enable_tqdm": bool(self.cfg.enable_tqdm),
            },
            "extra": self.extra_meta,
        }
        if self._web_url is not None:
            meta["viewer"] = {
                "url": self._web_url,
                "ready": bool(self._web_ready),
                "run_root": str(Path(self.run_root).resolve()),
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
        self._close_progress_bar()

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
        self._update_progress_bar(record)

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

    def _get_tqdm_cls(self) -> Any | None:
        if self._tqdm_checked:
            return self._tqdm_cls

        self._tqdm_checked = True
        try:
            from tqdm.auto import tqdm as tqdm_cls

            self._tqdm_cls = tqdm_cls
        except Exception:
            self._tqdm_cls = None
        return self._tqdm_cls

    def _update_progress_bar(self, record: Mapping[str, Any]) -> None:
        if not self.cfg.enable_tqdm:
            return

        tqdm_cls = self._get_tqdm_cls()
        if tqdm_cls is None:
            return

        step = int(record.get("step", 0))
        split = str(record.get("split", "train"))
        epoch_raw = record.get("epoch")
        epoch = int(epoch_raw) if epoch_raw is not None else None

        reopen = (
            self._pbar is None
            or split != self._pbar_last_split
            or epoch != self._pbar_last_epoch
            or (
                self._pbar_last_step is not None
                and step < self._pbar_last_step
            )
        )
        if reopen:
            self._close_progress_bar()
            desc = f"{self.name}:{split}"
            if epoch is not None:
                desc = f"{desc}:e{epoch}"
            self._pbar = tqdm_cls(
                total=None,
                desc=desc,
                leave=self.cfg.tqdm_leave,
                dynamic_ncols=self.cfg.tqdm_dynamic_ncols,
                mininterval=self.cfg.tqdm_mininterval,
                disable=not sys.stderr.isatty(),
            )
            self._pbar_last_step = step - 1

        delta = 1
        if self._pbar_last_step is not None:
            delta = max(1, step - self._pbar_last_step)

        if self._pbar is not None:
            self._pbar.update(delta)
            postfix: dict[str, str] = {}
            for key in ("loss", "acc", "lr", "gpu_mem_mb", "grad_norm"):
                value = record.get(key)
                if isinstance(value, (int, float)):
                    postfix[key] = f"{float(value):.4f}"
            if postfix:
                self._pbar.set_postfix(postfix, refresh=False)

        self._pbar_last_step = step
        self._pbar_last_split = split
        self._pbar_last_epoch = epoch

    def _close_progress_bar(self) -> None:
        if self._pbar is not None:
            try:
                self._pbar.close()
            except Exception:
                pass
        self._pbar = None
        self._pbar_last_step = None
        self._pbar_last_split = None
        self._pbar_last_epoch = None

    def _maybe_launch_web(self) -> None:
        if not self.cfg.auto_launch_web:
            return

        import importlib.util

        if importlib.util.find_spec("streamlit") is None:
            return

        run_root_abs = str(Path(self.run_root).expanduser().resolve())
        if self.cfg.web_once_per_process and run_root_abs in self._launched_web_roots:
            self._web_url = f"http://{self.cfg.web_host}:{self.cfg.web_port}"
        else:
            try:
                from torchlit.launch import launch_web

                launch_web(
                    run_root=run_root_abs,
                    host=self.cfg.web_host,
                    port=int(self.cfg.web_port),
                    open_browser=bool(self.cfg.web_open_browser),
                    wait=False,
                )
                self._launched_web_roots.add(run_root_abs)
                self._web_url = f"http://{self.cfg.web_host}:{self.cfg.web_port}"
            except Exception:
                self._web_url = None
                self._web_ready = False

        if self._web_url is not None and self.cfg.web_wait_ready:
            self._web_ready = self._wait_for_web_ready()
        else:
            self._web_ready = self._web_url is not None

    def _wait_for_web_ready(self) -> bool:
        if self._web_url is None:
            return False

        url = f"{self._web_url}/_stcore/health"
        deadline = time.monotonic() + max(0.0, float(self.cfg.web_ready_timeout_sec))
        poll_interval = max(0.05, float(self.cfg.web_ready_poll_interval_sec))

        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=1.5) as resp:
                    if int(getattr(resp, "status", 0)) == 200:
                        return True
            except (urllib.error.URLError, TimeoutError):
                time.sleep(poll_interval)
            except Exception:
                break

        return False

    @property
    def web_url(self) -> str | None:
        return self._web_url

    @property
    def web_ready(self) -> bool:
        return self._web_ready
