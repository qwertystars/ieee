"""
================================================================================
 ResQnet — BLE RSSI Synthetic Data Generator
================================================================================
Generates synthetic BLE RSSI measurements for indoor/outdoor localization.
Outputs a CSV with relay coordinates, RSSI readings, and survivor coordinates.
"""

import os
from typing import Tuple

import numpy as np
import pandas as pd

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────
NUM_SAMPLES = 20_000
NUM_RELAYS = 4
AREA_SIZE_M = 100.0
RANDOM_SEED = 42

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "data")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "ble_rssi_localization.csv")


def generate_dataset(
    num_samples: int = NUM_SAMPLES,
    num_relays: int = NUM_RELAYS,
    area_size_m: float = AREA_SIZE_M,
    seed: int = RANDOM_SEED,
) -> Tuple[pd.DataFrame, str]:
    rng = np.random.default_rng(seed)

    relay_coords = rng.uniform(
        low=0.0, high=area_size_m, size=(num_samples, num_relays, 2)
    )
    survivor_coords = rng.uniform(low=0.0, high=area_size_m, size=(num_samples, 2))

    deltas = relay_coords - survivor_coords[:, None, :]
    distances = np.linalg.norm(deltas, axis=2)
    distances = np.clip(distances, 1.0, None)

    path_loss_exp = rng.uniform(2.0, 4.5, size=(num_samples, num_relays))
    noise_sigma = rng.uniform(5.0, 10.0, size=(num_samples, num_relays))
    noise = rng.normal(0.0, noise_sigma)

    rssi = -50.0 - 10.0 * path_loss_exp * np.log10(distances) + noise

    data = {}
    for idx in range(num_relays):
        data[f"relay_{idx + 1}_x"] = np.round(relay_coords[:, idx, 0], 4)
        data[f"relay_{idx + 1}_y"] = np.round(relay_coords[:, idx, 1], 4)
        data[f"rssi_{idx + 1}"] = np.round(rssi[:, idx], 4)

    data["survivor_x"] = np.round(survivor_coords[:, 0], 4)
    data["survivor_y"] = np.round(survivor_coords[:, 1], 4)

    df = pd.DataFrame(data)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    df.to_csv(OUTPUT_FILE, index=False)

    return df, OUTPUT_FILE


if __name__ == "__main__":
    df_out, file_path = generate_dataset()
    print(f"[✓] Generated {len(df_out):,} samples")
    print(f"[✓] Output file: {file_path}")
