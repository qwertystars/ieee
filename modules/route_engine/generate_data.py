"""
================================================================================
 ResQnet — Block 1: Synthetic Disaster‑Road Data Generator
================================================================================
 Author : ResQnet AI/ML Engineering Team
 Purpose: Generates 50,000 synthetic road‑segment records that simulate real
          disaster conditions. Each row carries five sensor/intel inputs and a
          mathematically derived "Dynamic Traversal Penalty Score" (cost).
          This cost is the ground‑truth label the MLP will learn to predict.

 The generated CSV is consumed by the training pipeline (train_model.py).
================================================================================
"""

import numpy as np
import pandas as pd
import os

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────
NUM_SAMPLES      = 50_000          # Total synthetic road‑segment samples
RANDOM_SEED      = 42              # Reproducibility
OUTPUT_DIR       = os.path.join(os.path.dirname(__file__), "data")
OUTPUT_FILE      = os.path.join(OUTPUT_DIR, "disaster_road_data.csv")

np.random.seed(RANDOM_SEED)


# ──────────────────────────────────────────────────────────────────────────────
# Step 1 — Generate Raw Feature Distributions
# ──────────────────────────────────────────────────────────────────────────────
# Each feature is drawn from a distribution that mirrors realistic disaster
# telemetry.  We mix uniform and skewed distributions so the model sees both
# common (low‑risk) and rare (extreme) scenarios.

print("[*] Generating raw feature distributions …")

# Fire Risk (0 → 10): most roads have low/moderate fire risk; a minority are
# extreme (> 7).  We use a Beta distribution skewed left then scale to [0,10].
fire_risk = np.random.beta(a=2, b=5, size=NUM_SAMPLES) * 10.0

# Flood Level (0 → 10): roughly uniform — floods can hit any segment equally.
flood_level = np.random.uniform(low=0.0, high=10.0, size=NUM_SAMPLES)

# Structural Damage (0% → 100%): most structures survive partially; complete
# collapse is rarer.  Beta(2,3) gives a right‑skew.
structural_damage = np.random.beta(a=2, b=3, size=NUM_SAMPLES) * 100.0

# Survivor Urgency (0 → 10): bimodal — many segments have zero urgency
# (no survivors); some have critical urgency.
urgency_base = np.random.exponential(scale=3.0, size=NUM_SAMPLES)
survivor_urgency = np.clip(urgency_base, 0.0, 10.0)

# Distance (km): realistic urban/suburban road lengths (0.1 → 15 km).
distance_km = np.random.uniform(low=0.1, high=15.0, size=NUM_SAMPLES)


# ──────────────────────────────────────────────────────────────────────────────
# Step 2 — Compute Ground‑Truth Traversal Cost
# ──────────────────────────────────────────────────────────────────────────────
# The formula encodes domain knowledge about disaster navigation:
#
#   cost = (distance_penalty)
#        + (fire_penalty)          ← exponential, HIGH weight
#        + (flood_penalty)         ← linear,      MEDIUM weight
#        + (structural_penalty)    ← polynomial,  HIGH weight
#        - (urgency_attractor)     ← inverse cost, HIGH weight (pulls routes)
#        + (noise)
#
# The final cost is clamped to [0, ∞) — a negative cost is not physically
# meaningful, so any segment made "attractive" by survivor urgency still
# carries at least a small baseline cost.

print("[*] Computing ground‑truth traversal costs …")

# ── 2a. Distance Penalty (MEDIUM weight — linear baseline) ──────────────────
# Longer roads take proportionally more time.  Coefficient calibrated so a
# 10 km road contributes ~15 cost units at baseline.
distance_penalty = 1.5 * distance_km

# ── 2b. Fire Risk Penalty (HIGH weight — exponential) ────────────────────────
# Below risk 5 the penalty grows gently; above 7 it explodes, making the
# segment nearly impassable.
#   Formula:  0.8 * exp(0.55 * fire_risk)
# At fire_risk=7  → penalty ≈ 37
# At fire_risk=10 → penalty ≈ 196  (devastating)
fire_penalty = 0.8 * np.exp(0.55 * fire_risk)

# ── 2c. Flood Level Penalty (MEDIUM weight — linear/moderate) ────────────────
# Each unit of flood depth adds a steady cost.  Above depth 8, an additional
# quadratic bump reflects near‑impassability.
flood_penalty = 2.0 * flood_level + 0.15 * np.maximum(flood_level - 8.0, 0) ** 2

# ── 2d. Structural Damage Penalty (HIGH weight — polynomial curve) ───────────
# Partial damage is manageable; total collapse is a hard block.
#   Formula:  0.004 * damage^2 + 0.1 * damage
# At damage=50%  → penalty ≈ 15
# At damage=100% → penalty ≈ 50  (severe)
structural_penalty = 0.004 * structural_damage ** 2 + 0.1 * structural_damage

# ── 2e. Survivor Urgency Attractor (HIGH weight — cost reducer) ─────────────
# Critical survivors pull rescue teams toward the segment.  The attractor
# uses a square‑root curve so even moderate urgency has a meaningful draw,
# but the benefit saturates at extreme urgency (diminishing returns).
#   Formula:  5.0 * sqrt(urgency) + 0.8 * urgency
# At urgency=10 → attractor ≈ 23.8  (massive cost reduction)
urgency_attractor = 5.0 * np.sqrt(survivor_urgency) + 0.8 * survivor_urgency

# ── 2f. Gaussian Noise ──────────────────────────────────────────────────────
# Simulates sensor noise and unpredictable field conditions.
noise = np.random.normal(loc=0, scale=1.5, size=NUM_SAMPLES)

# ── 2g. Final Traversal Cost ────────────────────────────────────────────────
traversal_cost = (
    distance_penalty
    + fire_penalty
    + flood_penalty
    + structural_penalty
    - urgency_attractor      # negative = attractor (pulls route toward survivors)
    + noise
)

# Clamp to [0.1, ∞) — even the most attractive segment has a tiny baseline.
traversal_cost = np.maximum(traversal_cost, 0.1)


# ──────────────────────────────────────────────────────────────────────────────
# Step 3 — Assemble DataFrame and Persist
# ──────────────────────────────────────────────────────────────────────────────
print("[*] Assembling DataFrame …")

df = pd.DataFrame({
    "fire_risk":          np.round(fire_risk, 4),
    "flood_level":        np.round(flood_level, 4),
    "structural_damage":  np.round(structural_damage, 4),
    "survivor_urgency":   np.round(survivor_urgency, 4),
    "distance_km":        np.round(distance_km, 4),
    "traversal_cost":     np.round(traversal_cost, 4),
})

os.makedirs(OUTPUT_DIR, exist_ok=True)
df.to_csv(OUTPUT_FILE, index=False)

# ──────────────────────────────────────────────────────────────────────────────
# Step 4 — Summary Statistics (Sanity Check)
# ──────────────────────────────────────────────────────────────────────────────
print(f"\n{'=' * 60}")
print(f" ResQnet — Synthetic Data Generation Complete")
print(f"{'=' * 60}")
print(f" Rows generated : {len(df):,}")
print(f" Output file    : {OUTPUT_FILE}")
print(f"{'=' * 60}")
print(f"\n[Feature Statistics]")
print(df.describe().round(3).to_string())
print(f"\n[Target — traversal_cost]")
print(f"  Mean   : {df['traversal_cost'].mean():.3f}")
print(f"  Median : {df['traversal_cost'].median():.3f}")
print(f"  Min    : {df['traversal_cost'].min():.3f}")
print(f"  Max    : {df['traversal_cost'].max():.3f}")
print(f"  Std    : {df['traversal_cost'].std():.3f}")
print(f"\n[✓] Data generation finished successfully.\n")
