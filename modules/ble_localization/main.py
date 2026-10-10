"""
================================================================================
 ResQnet — BLE Localization FastAPI + CLI
================================================================================
Exposes a FastAPI endpoint for BLE RSSI localization and keeps a CLI helper.
"""

import argparse
import json
import os
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ble_localization.ble_train_model import (
    DATA_PATH,
    NUM_RELAYS,
    predict_location,
    _relay_cols,
    _rssi_cols,
)


class PredictRequest(BaseModel):
    relays: List[List[float]]


class SampleRequest(BaseModel):
    index: int


app = FastAPI(title="ResQnet BLE Localization API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class MeshEntry(BaseModel):
    survivor_id: str
    rssi: int
    relay_lat: float
    relay_lng: float
    relay_node_id: str
    hop_count: int = 0
    last_seen_ms: Optional[int] = None


class MeshSyncPayload(BaseModel):
    device_id: str
    device_lat: float
    device_lng: float
    timestamp: str
    survivor_count: int
    mesh_table: List[MeshEntry]


class ConnectionManager:
    def __init__(self) -> None:
        self.active: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active:
            self.active.remove(websocket)

    async def broadcast(self, message: Dict) -> None:
        living = []
        for socket in self.active:
            try:
                await socket.send_json(message)
                living.append(socket)
            except Exception:
                continue
        self.active = living


manager = ConnectionManager()
latest_state: Dict = {}


def _load_from_json(payload: str) -> np.ndarray:
    data = json.loads(payload)
    relay_array = np.asarray(data, dtype=np.float32)
    if relay_array.shape != (NUM_RELAYS, 3):
        raise ValueError(f"Expected relay data shape ({NUM_RELAYS}, 3).")
    return relay_array


def _load_from_relays(relays: List[List[float]]) -> np.ndarray:
    relay_array = np.asarray(relays, dtype=np.float32)
    if relay_array.shape != (NUM_RELAYS, 3):
        raise ValueError(f"Expected relay data shape ({NUM_RELAYS}, 3).")
    return relay_array


def _urgency_from_rssi(rssi: int) -> str:
    if rssi >= -55:
        return "high"
    if rssi >= -70:
        return "medium"
    return "low"


def _to_local_xy(relay_lat: float, relay_lng: float, device_lat: float, device_lng: float):
    scale = 10000.0
    x = (relay_lng - device_lng) * scale
    y = (relay_lat - device_lat) * scale
    x = max(min(x, 80.0), -80.0)
    y = max(min(y, 80.0), -80.0)
    return x, y


def _load_from_file(path: str) -> np.ndarray:
    with open(path, "r", encoding="utf-8") as f:
        return _load_from_json(f.read())


def _load_sample(index: int) -> np.ndarray:
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"Dataset not found at {DATA_PATH}.")

    df = pd.read_csv(DATA_PATH)
    if index < 0 or index >= len(df):
        raise IndexError(f"Sample index must be between 0 and {len(df) - 1}.")

    coords = df.loc[index, list(_relay_cols())].values.astype(np.float32).reshape(NUM_RELAYS, 2)
    rssi = df.loc[index, list(_rssi_cols())].values.astype(np.float32).reshape(NUM_RELAYS, 1)
    return np.concatenate([coords, rssi], axis=1)


def _build_route_state(payload: MeshSyncPayload) -> Dict:
    survivors = []
    hazards = []

    for entry in payload.mesh_table:
        x, y = _to_local_xy(entry.relay_lat, entry.relay_lng, payload.device_lat, payload.device_lng)
        survivors.append(
            {
                "id": entry.survivor_id,
                "x": x,
                "y": y,
                "lat": entry.relay_lat,
                "lng": entry.relay_lng,
                "urgency": _urgency_from_rssi(entry.rssi),
                "relay_node_id": entry.relay_node_id,
            }
        )
        if entry.rssi <= -85 or entry.hop_count >= 3:
            hazards.append({"x": x, "y": y, "z": 0.6})

    path = []
    if survivors:
        path.append({"x": 0.0, "y": 0.0, "z": 0.2})
        for survivor in survivors:
            path.append({"x": survivor["x"], "y": survivor["y"], "z": 0.4})

    return {"path": path, "survivors": survivors, "blocked_edges": hazards}


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/predict")
def predict(request: PredictRequest):
    try:
        relay_data = _load_from_relays(request.relays)
        pred_x, pred_y = predict_location(relay_data)
        return {"x": pred_x, "y": pred_y}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/predict/sample")
def predict_sample(request: SampleRequest):
    try:
        relay_data = _load_sample(request.index)
        pred_x, pred_y = predict_location(relay_data)
        return {"x": pred_x, "y": pred_y, "index": request.index}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/mesh/sync")
async def sync_mesh(payload: MeshSyncPayload):
    global latest_state
    latest_state = _build_route_state(payload)
    await manager.broadcast(latest_state)
    return {"ok": True, "survivors": len(payload.mesh_table)}


@app.post("/api/mesh/reset")
async def reset_mesh():
    global latest_state
    latest_state = {"path": [], "survivors": [], "blocked_edges": []}
    await manager.broadcast(latest_state)
    return {"ok": True}


@app.websocket("/ws/route")
async def route_ws(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        if latest_state:
            await websocket.send_json(latest_state)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Predict survivor coordinates from BLE relay RSSI data."
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--relay-json",
        help="Relay data as JSON array shaped (NUM_RELAYS, 3).",
    )
    group.add_argument(
        "--relay-file",
        help="Path to a JSON file containing relay data array.",
    )
    group.add_argument(
        "--sample-index",
        type=int,
        help="Use a sample row from the dataset by index.",
    )

    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if args.relay_json:
        relay_data = _load_from_json(args.relay_json)
    elif args.relay_file:
        relay_data = _load_from_file(args.relay_file)
    else:
        relay_data = _load_sample(args.sample_index)

    pred_x, pred_y = predict_location(relay_data)
    print(f"Predicted survivor location: x={pred_x:.2f}, y={pred_y:.2f}")


if __name__ == "__main__":
    main()
