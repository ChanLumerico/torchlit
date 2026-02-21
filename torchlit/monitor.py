import contextlib
import threading
import time
import requests
import queue
import psutil
from typing import Dict, Any, Optional

class Monitor(contextlib.ContextDecorator):
    def __init__(self, exp_name: str, server_url: str = "http://localhost:8000", flush_interval: float = 0.5):
        self.exp_name = exp_name
        self.server_url = server_url.rstrip("/")
        self.flush_interval = flush_interval
        
        self.queue = queue.Queue()
        self.is_running = False
        self.worker_thread: Optional[threading.Thread] = None

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
        }
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
            "sys_stats": self._get_system_stats()
        }
        
        try:
            requests.post(f"{self.server_url}/api/log", json=payload, timeout=1.0)
        except requests.RequestException:
            # We silently ignore connection errors to not crash training loop
            pass
