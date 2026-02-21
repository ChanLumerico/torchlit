import contextlib
import threading
import time
import requests
import queue
import psutil
from typing import Dict, Any, Optional

class Monitor(contextlib.ContextDecorator):
    """
    Context manager and decorator for monitoring PyTorch training loops.
    Sends real-time telemetry to the local torchlit visualization server.
    """
    def __init__(self, exp_name: str = "default_experiment", server_url: str = "http://localhost:8000", flush_interval: float = 1.0, model_info: Dict[str, Any] = None):
        self.exp_name = exp_name
        self.server_url = server_url.rstrip("/") # Keep rstrip as it's a good practice and not explicitly removed by instruction
        self.flush_interval = flush_interval
        self.model_info = model_info
        
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
            elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                self.device_type = "mps"
                self.device_name = "Apple Silicon (MPS)"
        except Exception:
            pass

    def __enter__(self):
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
            "model_info": self.model_info
        }
        
        try:
            requests.post(f"{self.server_url}/api/log", json=payload, timeout=1.0)
        except requests.RequestException:
            # We silently ignore connection errors to not crash training loop
            pass
