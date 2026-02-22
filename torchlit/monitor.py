import contextlib
import json
import os
import platform
import subprocess
import threading
import time
import requests
import queue
import psutil
import socket
import sys
from pathlib import Path
from typing import Dict, Any, Optional


def _get_bin_path() -> Path:
    """Return the path to the platform-specific torchlit-progress binary."""
    system = platform.system()  # Darwin, Linux, Windows
    machine = platform.machine()  # arm64, x86_64, AMD64

    if system == "Darwin":
        suffix = f"darwin-{machine}"  # darwin-arm64 | darwin-x86_64
    elif system == "Linux":
        suffix = f"linux-{machine}"  # linux-x86_64 | linux-aarch64
    elif system == "Windows":
        suffix = f"windows-x86_64.exe"  # windows-x86_64.exe
    else:
        suffix = None

    if suffix is None:
        return Path()  # Empty path — will not exist, falls back gracefully

    return Path(__file__).parent / "bin" / f"torchlit-progress-{suffix}"


_BIN_PATH = _get_bin_path()


class Monitor(contextlib.ContextDecorator):
    """
    Context manager and decorator for monitoring PyTorch training loops.
    Sends real-time telemetry to the local torchlit visualization server.
    Launches a Rust-based CLI display (torchlit-progress) for terminal progress.
    Falls back to plain text if the binary is not available.
    """

    def __init__(
        self,
        exp_name: str = "default_experiment",
        server_url: str | None = None,
        flush_interval: float = 1.0,
        model_info: Dict[str, Any] = None,
        model: Optional[Any] = None,
        optimizer: Optional[Any] = None,
        start_server: bool = True,
        total_steps: Optional[int] = None,
    ):
        self.exp_name = exp_name
        self.server_url = (
            server_url.rstrip("/") if server_url else "http://localhost:8000"
        )
        self.flush_interval = flush_interval
        self.model_info = model_info or {}
        self.model = model
        self.optimizer = optimizer
        self.start_server = start_server
        self.total_steps = total_steps

        if self.total_steps is not None:
            self.model_info["total_steps"] = self.total_steps

        self.queue = queue.Queue()
        self.is_running = False
        self.worker_thread: Optional[threading.Thread] = None

        # Hardware Detection (Cache once)
        self.device_type = "cpu"
        self.device_name = "CPU"
        self._torch = None

        try:
            import torch

            self._torch = torch
            if torch.cuda.is_available():
                self.device_type = "cuda"
                self.device_name = torch.cuda.get_device_name(0)
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                self.device_type = "mps"
                self.device_name = "Apple Silicon (MPS)"
        except Exception:
            pass

        # Auto-extract model info if provided
        if self.model is not None:
            self._extract_model_info()

        # Rust CLI display state
        self._cli_proc: Optional[subprocess.Popen] = None
        self._start_time: Optional[float] = None

    def _format_num(self, num: int) -> str:
        if num >= 1e9:
            return f"{num / 1e9:.1f} B"
        elif num >= 1e6:
            return f"{num / 1e6:.1f} M"
        elif num >= 1e3:
            return f"{num / 1e3:.1f} K"
        return str(num)

    def _extract_model_info(self):
        try:
            self.model_info["name"] = self.model_info.get(
                "name", self.model.__class__.__name__
            )

            # Count parameters
            total_params = sum(p.numel() for p in self.model.parameters())
            trainable_params = sum(
                p.numel() for p in self.model.parameters() if p.requires_grad
            )

            self.model_info["total_params"] = self.model_info.get(
                "total_params", self._format_num(total_params)
            )
            self.model_info["trainable_params"] = self.model_info.get(
                "trainable_params", self._format_num(trainable_params)
            )

            # Try to infer device from first parameter
            first_param = next(self.model.parameters(), None)
            if first_param is not None and hasattr(first_param, "device"):
                dev_type = first_param.device.type
                if dev_type == "cuda":
                    self.device_type = "cuda"
                    if self._torch and self._torch.cuda.is_available():
                        self.device_name = self._torch.cuda.get_device_name(
                            first_param.device.index or 0
                        )
                elif dev_type == "mps":
                    self.device_type = "mps"
                    self.device_name = "Apple Silicon (MPS)"
                elif dev_type == "cpu":
                    self.device_type = "cpu"
                    self.device_name = "CPU"

            # Extract architecture tree
            def _get_module_tree(module, name="Root"):
                children = list(module.named_children())
                node_params = sum(p.numel() for p in module.parameters(recurse=False))
                total_node_params = sum(p.numel() for p in module.parameters())

                node = {
                    "name": name,
                    "class_name": module.__class__.__name__,
                    "params": node_params,
                    "total_params": total_node_params,
                    "children": [],
                }

                for child_name, child_module in children:
                    node["children"].append(_get_module_tree(child_module, child_name))

                return node

            self.model_info["architecture"] = _get_module_tree(self.model)

        except Exception:
            pass

    def _start_server_if_needed(self):
        """Checks if port 8000 is open. If not, spawns the FastAPI server as a detached daemon."""
        try:
            from urllib.parse import urlparse

            port = urlparse(self.server_url).port or 8000
            host = urlparse(self.server_url).hostname or "localhost"

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.1)
                if s.connect_ex((host, port)) != 0:
                    print(
                        f"⚡ torchlit catching up! Spawning dashboard background server at {self.server_url}..."
                    )
                    subprocess.Popen(
                        [
                            sys.executable,
                            "-m",
                            "uvicorn",
                            "torchlit.backend.main:app",
                            "--port",
                            str(port),
                            "--log-level",
                            "error",
                            "--no-access-log",
                        ],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                    time.sleep(1.5)
        except Exception as e:
            print(f"⚠️ torchlit could not start background server: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # Rust CLI Display
    # ─────────────────────────────────────────────────────────────────────────

    def _write_cli(self, msg: dict) -> None:
        """Write a JSON message line to the Rust CLI process stdin."""
        if self._cli_proc is not None and self._cli_proc.poll() is None:
            try:
                line = json.dumps(msg) + "\n"
                self._cli_proc.stdin.write(line.encode())
                self._cli_proc.stdin.flush()
            except (BrokenPipeError, OSError):
                self._cli_proc = None

    def _start_cli(self) -> None:
        """Spawn the Rust CLI binary as a subprocess."""
        if not _BIN_PATH.exists():
            return  # Binary not compiled yet — skip silently

        try:
            self._cli_proc = subprocess.Popen(
                [str(_BIN_PATH)],
                stdin=subprocess.PIPE,
                stdout=None,  # inherit terminal
                stderr=subprocess.DEVNULL,
            )
            # Give Rust process a moment to initialize before writing
            time.sleep(0.15)
            # Send init message
            self._write_cli(
                {
                    "type": "init",
                    "exp_name": self.exp_name,
                    "model_name": self.model_info.get("name"),
                    "total_params": self.model_info.get("total_params"),
                    "trainable_params": self.model_info.get("trainable_params"),
                    "device": self.device_name,
                    "total_steps": self.total_steps,
                }
            )
        except Exception:
            self._cli_proc = None

    def _stop_cli(self, final_step: int = 0) -> None:
        """Send done message and wait for the Rust CLI to exit cleanly."""
        if self._cli_proc is None:
            return
        try:
            self._write_cli({"type": "done", "step": final_step})
            self._cli_proc.stdin.close()
            self._cli_proc.wait(timeout=5)
        except Exception:
            try:
                self._cli_proc.terminate()
            except Exception:
                pass
        self._cli_proc = None

    # ─────────────────────────────────────────────────────────────────────────

    def __enter__(self):
        if self.start_server:
            self._start_server_if_needed()

        self._start_time = time.time()
        self.is_running = True
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()

        self._start_cli()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.is_running = False
        if self.worker_thread is not None:
            self.worker_thread.join(timeout=2.0)

        # Flush remaining queued items
        self._flush_queue()

        self._stop_cli(final_step=self._last_step)

        if self.start_server:
            try:
                requests.post(
                    f"{self.server_url}/api/status",
                    json={"status": "finished"},
                    timeout=1.0,
                )
                print(
                    f"⚡ torchlit training complete! Dashboard stays active at {self.server_url}"
                )
                print(
                    "   (It will automatically shut down when you close the browser window)"
                )
            except requests.RequestException:
                pass

        return False

    _last_step: int = 0

    def log(self, metrics: Dict[str, Any], step: int):
        """Queue metrics for the server and push to the Rust CLI display."""
        self._last_step = step
        elapsed = time.time() - self._start_time if self._start_time else 0.0

        self.queue.put({"step": step, "metrics": metrics})

        # Push to Rust TUI
        self._write_cli(
            {
                "type": "step",
                "step": step,
                "metrics": metrics,
                "elapsed": elapsed,
            }
        )

    def _get_system_stats(self) -> Dict[str, Any]:
        """Collect system usage metrics"""
        stats = {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "ram_percent": psutil.virtual_memory().percent,
            "device_type": self.device_type,
            "device_name": self.device_name,
            "vram_percent": None,
        }

        if self._torch is not None:
            try:
                if self.device_type == "cuda":
                    mem_alloc = self._torch.cuda.memory_allocated(0)
                    mem_total = self._torch.cuda.get_device_properties(0).total_memory
                    if mem_total > 0:
                        stats["vram_percent"] = (mem_alloc / mem_total) * 100
                elif self.device_type == "mps":
                    alloc = self._torch.mps.current_allocated_memory()
                    total = psutil.virtual_memory().total
                    stats["vram_percent"] = (alloc / total) * 100
            except Exception:
                pass

        return stats

    def _worker_loop(self):
        """Background thread loop to send data"""
        while self.is_running:
            self._flush_queue()
            time.sleep(self.flush_interval)

    def _flush_queue(self):
        """Send all items currently in the queue"""
        while not self.queue.empty():
            try:
                item = self.queue.get_nowait()
                self._send_data(int(item["step"]), dict(item["metrics"]))
                self.queue.task_done()
            except queue.Empty:
                break

    def _send_data(self, step: int, metrics: Dict[str, Any]):
        """Perform the actual HTTP POST request"""
        payload = {
            "exp_name": self.exp_name,
            "step": step,
            "metrics": metrics,
            "sys_stats": self._get_system_stats(),
            "model_info": self.model_info if step == 1 else {},
        }

        try:
            requests.post(f"{self.server_url}/api/log", json=payload, timeout=1.0)
        except requests.RequestException:
            pass
