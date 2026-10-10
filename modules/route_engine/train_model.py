"""
================================================================================
 ResQnet — Block 3: Training Loop & Model Export
================================================================================
 Author : ResQnet AI/ML Engineering Team
 Purpose: Loads the synthetic disaster‑road data, normalises features with
          StandardScaler, trains the DisasterRoutePredictor MLP, and exports:
            • rescue_ai_weights.pth  — trained PyTorch model state dict
            • scaler.pkl             — fitted StandardScaler for inference

 Training Details
 ────────────────
 • Loss      : MSELoss (regression on traversal cost)
 • Optimiser : Adam (lr=1e-3, weight_decay=1e-5 for L2 regularisation)
 • Scheduler : ReduceLROnPlateau — halves LR if validation loss stalls
 • Epochs    : 50
 • Device    : CUDA if available, else CPU
================================================================================
"""

import os
import time
import pickle

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

# Local import — the MLP architecture from Block 2
from model import DisasterRoutePredictor


# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────
DATA_PATH       = os.path.join(os.path.dirname(__file__), "data", "disaster_road_data.csv")
WEIGHTS_PATH    = os.path.join(os.path.dirname(__file__), "weights", "rescue_ai_weights.pth")
SCALER_PATH     = os.path.join(os.path.dirname(__file__), "weights", "scaler.pkl")

BATCH_SIZE      = 512
EPOCHS          = 50
LEARNING_RATE   = 1e-3
WEIGHT_DECAY    = 1e-5          # L2 regularisation coefficient
TEST_SPLIT      = 0.15          # 15 % held out for validation
RANDOM_SEED     = 42
PRINT_EVERY     = 10            # Print loss every N epochs

# ──────────────────────────────────────────────────────────────────────────────
# Device Selection — CUDA → CPU fallback
# ──────────────────────────────────────────────────────────────────────────────
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"[*] Using device: {device}")
if device.type == "cuda":
    print(f"    GPU: {torch.cuda.get_device_name(0)}")
    print(f"    VRAM: {torch.cuda.get_device_properties(0).total_mem / 1e9:.1f} GB")


# ──────────────────────────────────────────────────────────────────────────────
# Step 1 — Load & Prepare Data
# ──────────────────────────────────────────────────────────────────────────────
print(f"\n[1/5] Loading data from: {DATA_PATH}")
df = pd.read_csv(DATA_PATH)
print(f"      Loaded {len(df):,} rows × {df.shape[1]} columns.")

FEATURE_COLS = ["fire_risk", "flood_level", "structural_damage",
                "survivor_urgency", "distance_km"]
TARGET_COL   = "traversal_cost"

X = df[FEATURE_COLS].values.astype(np.float32)
y = df[TARGET_COL].values.astype(np.float32).reshape(-1, 1)


# ──────────────────────────────────────────────────────────────────────────────
# Step 2 — Feature Scaling (StandardScaler)
# ──────────────────────────────────────────────────────────────────────────────
print("[2/5] Fitting StandardScaler on features …")
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X).astype(np.float32)

# Persist the scaler so inference uses the same normalisation
os.makedirs(os.path.dirname(SCALER_PATH), exist_ok=True)
with open(SCALER_PATH, "wb") as f:
    pickle.dump(scaler, f)
print(f"      Scaler saved → {SCALER_PATH}")


# ──────────────────────────────────────────────────────────────────────────────
# Step 3 — Train / Validation Split & DataLoaders
# ──────────────────────────────────────────────────────────────────────────────
print(f"[3/5] Splitting data ({int((1-TEST_SPLIT)*100)}% train / {int(TEST_SPLIT*100)}% val) …")

X_train, X_val, y_train, y_val = train_test_split(
    X_scaled, y, test_size=TEST_SPLIT, random_state=RANDOM_SEED
)

# Convert to PyTorch tensors
X_train_t = torch.tensor(X_train, dtype=torch.float32)
y_train_t = torch.tensor(y_train, dtype=torch.float32)
X_val_t   = torch.tensor(X_val,   dtype=torch.float32)
y_val_t   = torch.tensor(y_val,   dtype=torch.float32)

train_dataset = TensorDataset(X_train_t, y_train_t)
val_dataset   = TensorDataset(X_val_t,   y_val_t)

train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True,
                           pin_memory=(device.type == "cuda"))
val_loader   = DataLoader(val_dataset,   batch_size=BATCH_SIZE, shuffle=False,
                           pin_memory=(device.type == "cuda"))

print(f"      Train samples : {len(train_dataset):,}")
print(f"      Val samples   : {len(val_dataset):,}")


# ──────────────────────────────────────────────────────────────────────────────
# Step 4 — Instantiate Model, Loss, Optimiser, Scheduler
# ──────────────────────────────────────────────────────────────────────────────
print("[4/5] Building model …")

model = DisasterRoutePredictor(input_dim=5).to(device)
criterion = nn.MSELoss()
optimizer = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE,
                              weight_decay=WEIGHT_DECAY)
scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
    optimizer, mode="min", factor=0.5, patience=5
)

total_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
print(f"      Architecture : 5 → 128 → 64 → 32 → 1")
print(f"      Parameters   : {total_params:,}")
print(f"      Optimiser    : Adam (lr={LEARNING_RATE}, wd={WEIGHT_DECAY})")
print(f"      Loss         : MSELoss")
print(f"      Scheduler    : ReduceLROnPlateau (factor=0.5, patience=5)")


# ──────────────────────────────────────────────────────────────────────────────
# Step 5 — Training Loop
# ──────────────────────────────────────────────────────────────────────────────
print(f"\n{'=' * 70}")
print(f" TRAINING — {EPOCHS} Epochs")
print(f"{'=' * 70}")

best_val_loss = float("inf")
train_start = time.time()

for epoch in range(1, EPOCHS + 1):
    # ── Training Phase ───────────────────────────────────────────────────
    model.train()
    epoch_train_loss = 0.0

    for batch_X, batch_y in train_loader:
        batch_X = batch_X.to(device)
        batch_y = batch_y.to(device)

        # Forward pass
        predictions = model(batch_X)
        loss = criterion(predictions, batch_y)

        # Backward pass
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        epoch_train_loss += loss.item() * batch_X.size(0)

    avg_train_loss = epoch_train_loss / len(train_dataset)

    # ── Validation Phase ─────────────────────────────────────────────────
    model.eval()
    epoch_val_loss = 0.0

    with torch.no_grad():
        for batch_X, batch_y in val_loader:
            batch_X = batch_X.to(device)
            batch_y = batch_y.to(device)

            predictions = model(batch_X)
            loss = criterion(predictions, batch_y)
            epoch_val_loss += loss.item() * batch_X.size(0)

    avg_val_loss = epoch_val_loss / len(val_dataset)

    # Step the LR scheduler based on validation loss
    scheduler.step(avg_val_loss)

    # ── Checkpoint best model ────────────────────────────────────────────
    if avg_val_loss < best_val_loss:
        best_val_loss = avg_val_loss
        best_state = model.state_dict().copy()

    # ── Logging ──────────────────────────────────────────────────────────
    if epoch % PRINT_EVERY == 0 or epoch == 1:
        current_lr = optimizer.param_groups[0]["lr"]
        elapsed = time.time() - train_start
        print(
            f"  Epoch {epoch:>3}/{EPOCHS}  │  "
            f"Train Loss: {avg_train_loss:>10.4f}  │  "
            f"Val Loss: {avg_val_loss:>10.4f}  │  "
            f"LR: {current_lr:.1e}  │  "
            f"Time: {elapsed:>6.1f}s"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Step 6 — Save Best Model Weights
# ──────────────────────────────────────────────────────────────────────────────
elapsed_total = time.time() - train_start

# Restore best checkpoint before saving
model.load_state_dict(best_state)
os.makedirs(os.path.dirname(WEIGHTS_PATH), exist_ok=True)
torch.save(model.state_dict(), WEIGHTS_PATH)

print(f"\n{'=' * 70}")
print(f" TRAINING COMPLETE")
print(f"{'=' * 70}")
print(f"  Total time     : {elapsed_total:.1f}s")
print(f"  Best Val Loss  : {best_val_loss:.4f}")
print(f"  Best Val RMSE  : {best_val_loss ** 0.5:.4f}")
print(f"  Model saved    → {WEIGHTS_PATH}")
print(f"  Scaler saved   → {SCALER_PATH}")
print(f"{'=' * 70}\n")


# ──────────────────────────────────────────────────────────────────────────────
# Step 7 — Quick Inference Sanity Check
# ──────────────────────────────────────────────────────────────────────────────
print("[✓] Running inference sanity check on 3 synthetic scenarios …\n")

test_scenarios = pd.DataFrame({
    "fire_risk":         [1.0,   9.5,   3.0],
    "flood_level":       [0.5,   2.0,   8.5],
    "structural_damage": [10.0,  95.0,  40.0],
    "survivor_urgency":  [2.0,   0.5,   9.5],
    "distance_km":       [3.0,   5.0,   2.0],
}, index=["Safe Road", "Inferno + Collapse", "Flooded but Critical Survivors"])

test_X = scaler.transform(test_scenarios.values.astype(np.float32))
test_tensor = torch.tensor(test_X, dtype=torch.float32).to(device)

model.eval()
with torch.no_grad():
    preds = model(test_tensor).cpu().numpy().flatten()

for i, (name, row) in enumerate(test_scenarios.iterrows()):
    print(f"  Scenario: {name}")
    print(f"    Fire={row['fire_risk']:.1f}  Flood={row['flood_level']:.1f}  "
          f"Damage={row['structural_damage']:.0f}%  "
          f"Urgency={row['survivor_urgency']:.1f}  Dist={row['distance_km']:.1f}km")
    print(f"    → Predicted Traversal Cost: {preds[i]:.4f}")
    print()

print("[✓] All blocks completed. Model is ready for Dijkstra integration.\n")
