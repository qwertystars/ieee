"""
================================================================================
 ResQnet — BLE RSSI Localization Training Pipeline
================================================================================
Trains a BLE RSSI-based indoor/outdoor localization model and exports:
  • survivor_locator.pth  — trained PyTorch state dict
  • loc_scaler.pkl         — StandardScaler fitted on RSSI readings
Also generates a matplotlib visualization of a sample prediction.
"""

import os
import time
import pickle
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import matplotlib.pyplot as plt

from ble_localization.ble_model import SurvivorLocatorMLP
from ble_localization.ble_generate_data import generate_dataset


DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "ble_rssi_localization.csv")
WEIGHTS_PATH = os.path.join(os.path.dirname(__file__), "weights", "survivor_locator.pth")
SCALER_PATH = os.path.join(os.path.dirname(__file__), "weights", "loc_scaler.pkl")
PLOT_PATH = os.path.join(os.path.dirname(__file__), "weights", "sample_localization_plot.png")

NUM_RELAYS = 4
BATCH_SIZE = 512
EPOCHS = 80
LEARNING_RATE = 1e-3
TEST_SPLIT = 0.2
RANDOM_SEED = 42
PRINT_EVERY = 10


def _device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def _relay_cols():
    cols = []
    for i in range(NUM_RELAYS):
        cols.append(f"relay_{i + 1}_x")
        cols.append(f"relay_{i + 1}_y")
    return tuple(cols)


def _rssi_cols():
    return tuple(f"rssi_{i + 1}" for i in range(NUM_RELAYS))


def load_and_prepare_data(data_path: str):
    df = pd.read_csv(data_path)
    relay_coords = df[list(_relay_cols())].values.astype(np.float32)
    rssi = df[list(_rssi_cols())].values.astype(np.float32)
    targets = df[["survivor_x", "survivor_y"]].values.astype(np.float32)
    return relay_coords, rssi, targets


def train_model(
    relay_coords: np.ndarray, rssi: np.ndarray, targets: np.ndarray, indices: np.ndarray
):
    device = _device()
    (
        coords_train,
        coords_val,
        rssi_train,
        rssi_val,
        y_train,
        y_val,
        _,
        idx_val,
    ) = train_test_split(
        relay_coords,
        rssi,
        targets,
        indices,
        test_size=TEST_SPLIT,
        random_state=RANDOM_SEED,
    )

    scaler = StandardScaler()
    rssi_train_scaled = scaler.fit_transform(rssi_train).astype(np.float32)
    rssi_val_scaled = scaler.transform(rssi_val).astype(np.float32)

    X_train = np.concatenate([coords_train, rssi_train_scaled], axis=1).astype(np.float32)
    X_val = np.concatenate([coords_val, rssi_val_scaled], axis=1).astype(np.float32)

    train_ds = TensorDataset(torch.tensor(X_train), torch.tensor(y_train))
    val_ds = TensorDataset(torch.tensor(X_val), torch.tensor(y_val))
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False)

    model = SurvivorLocatorMLP(input_dim=X_train.shape[1]).to(device)
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE)

    best_val = float("inf")
    best_state = None
    start = time.time()

    for epoch in range(1, EPOCHS + 1):
        model.train()
        train_loss = 0.0
        for batch_X, batch_y in train_loader:
            batch_X = batch_X.to(device)
            batch_y = batch_y.to(device)
            preds = model(batch_X)
            loss = criterion(preds, batch_y)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * batch_X.size(0)

        avg_train = train_loss / len(train_ds)
        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for batch_X, batch_y in val_loader:
                batch_X = batch_X.to(device)
                batch_y = batch_y.to(device)
                preds = model(batch_X)
                loss = criterion(preds, batch_y)
                val_loss += loss.item() * batch_X.size(0)

        avg_val = val_loss / len(val_ds)
        if avg_val < best_val:
            best_val = avg_val
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

        if epoch == 1 or epoch % PRINT_EVERY == 0:
            elapsed = time.time() - start
            print(
                f"Epoch {epoch:>3}/{EPOCHS} | "
                f"Train {avg_train:>8.4f} | "
                f"Val {avg_val:>8.4f} | "
                f"Time {elapsed:>6.1f}s"
            )

    if best_state is not None:
        model.load_state_dict(best_state)

    return model, idx_val, scaler, device


def predict_location(
    relay_data: np.ndarray,
    model_path: str = WEIGHTS_PATH,
    scaler_path: str = SCALER_PATH,
    device: Optional[torch.device] = None,
) -> Tuple[float, float]:
    relay_array = np.asarray(relay_data, dtype=np.float32)
    if relay_array.shape != (NUM_RELAYS, 3):
        raise ValueError(f"relay_data must have shape ({NUM_RELAYS}, 3).")

    coords = relay_array[:, :2].reshape(1, -1)
    rssi = relay_array[:, 2].reshape(1, -1)

    with open(scaler_path, "rb") as f:
        scaler = pickle.load(f)

    rssi_scaled = scaler.transform(rssi).astype(np.float32)
    features = np.concatenate([coords, rssi_scaled], axis=1).astype(np.float32)

    device = device or _device()
    model = SurvivorLocatorMLP(input_dim=features.shape[1]).to(device)
    state = torch.load(model_path, map_location=device)
    model.load_state_dict(state)
    model.eval()

    with torch.no_grad():
        pred = model(torch.tensor(features, device=device)).cpu().numpy()[0]
    return float(pred[0]), float(pred[1])


def plot_sample_case(relay_data: np.ndarray, true_xy: np.ndarray, pred_xy, save_path: str = PLOT_PATH):
    relay_coords = relay_data[:, :2]
    true_x, true_y = true_xy
    pred_x, pred_y = pred_xy
    error_radius = float(np.linalg.norm(np.array([pred_x - true_x, pred_y - true_y])))

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(relay_coords[:, 0], relay_coords[:, 1], marker="s", s=80, label="Relays")
    ax.scatter(true_x, true_y, marker="*", s=160, label="True Survivor")
    ax.scatter(pred_x, pred_y, marker="x", s=120, label="Predicted")
    circle = plt.Circle((true_x, true_y), error_radius, fill=False, linestyle="--")
    ax.add_patch(circle)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.set_aspect("equal", adjustable="box")
    ax.legend()
    ax.grid(True, linestyle=":", linewidth=0.7)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    if not os.path.exists(DATA_PATH):
        print("[*] Synthetic dataset not found. Generating...")
        generate_dataset()

    relay_coords, rssi_raw, targets = load_and_prepare_data(DATA_PATH)
    indices = np.arange(len(targets))
    model, val_indices, scaler, device = train_model(relay_coords, rssi_raw, targets, indices)

    os.makedirs(os.path.dirname(SCALER_PATH), exist_ok=True)
    with open(SCALER_PATH, "wb") as f:
        pickle.dump(scaler, f)
    torch.save(model.state_dict(), WEIGHTS_PATH)

    df_all = pd.read_csv(DATA_PATH)
    sample_idx = int(np.random.default_rng(RANDOM_SEED).choice(val_indices))
    relay_input = np.column_stack(
        [
            df_all.loc[sample_idx, list(_relay_cols())].values.astype(np.float32).reshape(NUM_RELAYS, 2),
            df_all.loc[sample_idx, list(_rssi_cols())].values.astype(np.float32).reshape(NUM_RELAYS, 1),
        ]
    )
    true_xy = df_all.loc[sample_idx, ["survivor_x", "survivor_y"]].values.astype(np.float32)
    pred_xy = predict_location(relay_input, device=device)
    plot_sample_case(relay_input, true_xy, pred_xy)
