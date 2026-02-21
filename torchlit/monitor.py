import contextlib
import threading
import time
import requests
import queue
import psutil
import socket
import subprocess
import sys
from typing import Dict, Any, Optional


class Monitor(contextlib.ContextDecorator):
    """
    Context manager and decorator for monitoring PyTorch training loops.
    Sends real-time telemetry to the local torchlit visualization server.
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
        except Exception as e:
            # Silently fail if model is not a standard PyTorch module
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
                        start_new_session=True,  # Make it a daemon
                    )
                    time.sleep(1.5)  # Give it a moment to boot
        except Exception as e:
            print(f"⚠️ torchlit could not start background server: {e}")

    def __enter__(self):
        if self.start_server:
            self._start_server_if_needed()

        self.is_running = True
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.is_running = False
        if self.worker_thread is not None:
            self.worker_thread.join(timeout=2.0)

        # Flush remaining queued items
        self._flush_queue()

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

        return False  # Do not suppress exceptions

    def log(self, metrics: Dict[str, Any], step: int):
        """Queue metrics to be sent to the server"""
        self.queue.put({"step": step, "metrics": metrics})

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
                    # Apple Silicon unified memory VRAM proxy
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
            "model_info": self.model_info,
        }

        try:
            requests.post(f"{self.server_url}/api/log", json=payload, timeout=1.0)
        except requests.RequestException:
            # We silently ignore connection errors to not crash training loop
            pass
