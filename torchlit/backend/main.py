from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Dict, List, Any
import asyncio
import os
from collections import defaultdict, deque

app = FastAPI(title="torchlit broker")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage for metrics. structure:
# {
#    "experiment_name": deque([metric_dict, metric_dict, ...], maxlen=1000)
# }
experiment_metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))

# Connected websocket clients per experiment
# {
#    "experiment_name": [websocket1, websocket2, ...]
# }
active_connections: Dict[str, List[WebSocket]] = defaultdict(list)


class MetricLog(BaseModel):
    exp_name: str
    step: int
    metrics: Dict[str, Any]
    sys_stats: Dict[str, Any]
    model_info: Dict[str, Any] = None


@app.post("/api/log")
async def log_metrics(log_data: MetricLog):
    """
    Receive metrics from the torchlit python client and broadcast to connected frontends.
    """
    exp_name = log_data.exp_name
    data_point = log_data.dict()
    
    # Store in memory cache
    experiment_metrics[exp_name].append(data_point)
    
    # Broadcast to connected clients for this experiment
    if exp_name in active_connections:
        dead_connections = []
        for connection in active_connections[exp_name]:
            try:
                await connection.send_json(data_point)
            except Exception:
                dead_connections.append(connection)
        
        # Cleanup dead connections
        for dead in dead_connections:
            active_connections[exp_name].remove(dead)
            
    return {"status": "ok"}


@app.websocket("/ws/stream/{exp_name}")
async def websocket_endpoint(websocket: WebSocket, exp_name: str):
    """
    WebSocket endpoint for frontend to receive live real-time metrics for a specific experiment.
    On connection, rehydrate with the last N cached metrics.
    """
    await websocket.accept()
    active_connections[exp_name].append(websocket)
    
    try:
        # Rehydrate existing data
        if exp_name in experiment_metrics and len(experiment_metrics[exp_name]) > 0:
            # Send all historical metrics
            for data_point in list(experiment_metrics[exp_name]):
                await websocket.send_json(data_point)
                
        # Keep connection alive
        while True:
            # Wait for any messages from client (e.g. ping)
            await websocket.receive_text()
            
    except WebSocketDisconnect:
        active_connections[exp_name].remove(websocket)
        if not active_connections[exp_name]:
            del active_connections[exp_name]

@app.get("/api/experiments")
async def list_experiments():
    """List all active experiments"""
    return {"experiments": list(experiment_metrics.keys())}


# --- Serve Frontend SPA ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIST = os.path.join(BASE_DIR, "..", "frontend", "dist")
FRONTEND_ASSETS = os.path.join(FRONTEND_DIST, "assets")

if os.path.exists(FRONTEND_ASSETS):
    app.mount("/assets", StaticFiles(directory=FRONTEND_ASSETS), name="assets")

@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    """Fallback route to serve the React SPA index.html for all non-API paths."""
    # Check if we have the built frontend
    index_path = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.exists(index_path):
        # We explicitly serve index.html and let React handle the client-side routing
        return FileResponse(index_path)
    
    return {"error": "Frontend build not found. Run 'npm run build' inside torchlit/frontend"}

