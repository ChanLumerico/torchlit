# torchlit 🔥
<p align="center">
  <b>A lightweight, beautiful, and interactive real-time PyTorch training dashboard.</b>
</p>

`torchlit` is a zero-setup desktop GUI that hooks directly into your PyTorch training loops to monitor metrics, system stats, and model insights. Stop relying on cluttered TQDM progress bars or heavy logging frameworks for local experimentation.

## ✨ Features
* **Zero Configuration:** Just use `with torchlit.Monitor():` and watch your local server instantly spin up.
* **Real-Time Streaming:** Built with FastAPI and WebSockets to push metrics to your browser immediately.
* **Auto-Discovery:** Automatically logs model parameter counts, activation memory sizes, and layer outlines.
* **Multi-Session Comparison:** Compare different experiments side-by-side with overlaid data lines.
* **System Resource Sparklines:** Live historical tracking of CPU and VRAM usage.
* **CSV Export:** Download all aggregated metrics at any time for offline analysis.
* **Auto-Shutdown:** Cleanly cleans up background uvicorn servers when your python script stops.

## 🚀 Quick Start
```python
import torch
import torchlit
import time

# Create a mock model
model = torch.nn.Sequential(
    torch.nn.Linear(10, 50),
    torch.nn.ReLU(),
    torch.nn.Linear(50, 2)
)

# Start logging with a single line
with torchlit.Monitor(exp_name="MyFirstExperiment", model=model) as logger:
    
    # Simulate a training loop
    for epoch in range(1, 101):
        loss = max(0, 1.0 - (epoch * 0.01))
        
        # Log your metrics
        logger.log({
            "loss": loss,
            "accuracy": epoch / 100.0,
            "learning_rate": 0.001
        }, step=epoch)
        
        time.sleep(0.5)
```
*Run your script, and your browser will automatically open to `http://localhost:8000` showing a beautiful React dashboard!*

## 📦 Usage
Check out the `examples/example.py` for a full CIFAR-10 ResNet-50 mock training loop that demonstrates all of `torchlit`'s capabilities.
