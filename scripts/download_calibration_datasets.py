#!/usr/bin/env python3
"""Download public flood/damage datasets for conformal calibration.

Usage:
    python scripts/download_calibration_datasets.py                # download all accessible
    python scripts/download_calibration_datasets.py --dataset sen1floods11
    python scripts/download_calibration_datasets.py --list         # show dataset status

Acquires public real flood/damage datasets and converts them into the
calibration_data X/y format expected by ConformalCalibrator.fit.

Datasets:
    - Sen1Floods11: CC BY 4.0, direct download from GCS (public, no auth)
    - xBD: non-commercial research license, registration required at xView2
    - UNOSAT / Copernicus EMS: per-product, registration required (not attempted)

Output:
    backend/data/calibration/sen1floods11/X.npy  — feature matrix [n, 5]
    backend/data/calibration/sen1floods11/y.npy  — target vector [n]
    backend/data/calibration/manifest.json       — checksums + metadata

The output directory is gitignored — large GeoTIFFs are not committed.

Sen1Floods11 citation:
    Bonafilia, D., Tellman, B., Anderson, T., Issenberg, E. 2020.
    "Sen1Floods11: a georeferenced dataset to train and test deep learning
    flood algorithms for Sentinel-1." CVPRW 2020, pp. 210-211.
    License: CC BY 4.0 — https://creativecommons.org/licenses/by/4.0/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request

import numpy as np

# --- Paths ---
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.join(_SCRIPT_DIR, "..", "backend")
_OUT_DIR = os.path.join(_BACKEND_DIR, "data", "calibration")

# --- Sen1Floods11 config ---
_GCS_BASE = "https://storage.googleapis.com/sen1floods11"
_BUCKET_LIST = "https://storage.googleapis.com/storage/v1/b/sen1floods11/o"
_LABEL_PREFIX = "v1.1/data/flood_events/HandLabeled/LabelHand/"
_S1_PREFIX = "v1.1/data/flood_events/HandLabeled/S1Hand/"
_MAX_CHIPS = 60  # subset for calibration (full dataset is 446 chips, ~14 GB)
_REQUEST_DELAY = 0.1  # be polite to GCS


def _list_chips() -> list[str]:
    """List all chip IDs from the GCS bucket (LabelHand folder)."""
    all_names: list[str] = []
    page_token = None
    while True:
        url = f"{_BUCKET_LIST}?maxResults=1000&prefix={_LABEL_PREFIX}"
        if page_token:
            url += f"&pageToken={page_token}"
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.load(resp)
        for item in data.get("items", []):
            fname = item["name"].split("/")[-1]  # e.g. Bolivia_103757_LabelHand.tif
            chip_id = fname.replace("_LabelHand.tif", "")
            all_names.append(chip_id)
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return all_names


def _balanced_sample(chips: list[str], n: int) -> list[str]:
    """Sample n chips balanced across events (by country prefix)."""
    by_event: dict[str, list[str]] = {}
    for chip in chips:
        event = chip.split("_")[0]
        by_event.setdefault(event, []).append(chip)
    per_event = max(1, n // len(by_event))
    selected: list[str] = []
    for event, event_chips in sorted(by_event.items()):
        selected.extend(event_chips[:per_event])
    return selected[:n]


def _download(url: str, dest: str) -> bool:
    """Download a file with retry. Returns True on success."""
    for attempt in range(3):
        try:
            urllib.request.urlretrieve(url, dest)
            return True
        except Exception as exc:  # noqa: BLE001
            if attempt == 2:
                print(f"  FAILED (3 attempts): {exc}", file=sys.stderr)
                return False
            time.sleep(1.0)
    return False


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _extract_features(s1_path: str, label_path: str) -> tuple[list[float], float] | None:
    """Extract calibration features from one Sen1Floods11 chip.

    X = [mean_vv, mean_vh, vv_vh_diff, std_vv, std_vh]
    y = water_fraction (fraction of valid pixels labeled 1)
    """
    try:
        import rasterio
    except ImportError:
        print("ERROR: rasterio not installed", file=sys.stderr)
        return None

    try:
        with rasterio.open(s1_path) as ds:
            s1 = ds.read()  # shape (2, 512, 512): band 0=VV, band 1=VH
        with rasterio.open(label_path) as ds:
            label = ds.read(1)  # shape (512, 512), int16
    except Exception as exc:  # noqa: BLE001
        print(f"  rasterio error: {exc}", file=sys.stderr)
        return None

    vv = s1[0]
    vh = s1[1]
    valid = label != -1  # exclude NoData
    if not np.any(valid):
        return None

    vv_valid = vv[valid]
    vh_valid = vh[valid]
    # Handle NaN in SAR data
    vv_finite = vv_valid[np.isfinite(vv_valid)]
    vh_finite = vh_valid[np.isfinite(vh_valid)]
    if len(vv_finite) == 0 or len(vh_finite) == 0:
        return None

    mean_vv = float(np.mean(vv_finite))
    mean_vh = float(np.mean(vh_finite))
    vv_vh_diff = mean_vv - mean_vh
    std_vv = float(np.std(vv_finite))
    std_vh = float(np.std(vh_finite))
    water_fraction = float(np.mean(label[valid] == 1))

    return [mean_vv, mean_vh, vv_vh_diff, std_vv, std_vh], water_fraction


def download_sen1floods11(out_dir: str) -> dict:
    """Download Sen1Floods11 subset and convert to X/y arrays.

    Returns manifest dict with chip count, checksums, and feature metadata.
    """
    print("=== Sen1Floods11 (CC BY 4.0) ===")
    print("Listing chips from GCS bucket...")
    all_chips = _list_chips()
    print(f"  Found {len(all_chips)} chips across "
          f"{len(set(c.split('_')[0] for c in all_chips))} events")

    selected = _balanced_sample(all_chips, _MAX_CHIPS)
    print(f"  Selected {len(selected)} chips (balanced across events)")

    chip_dir = os.path.join(out_dir, "sen1floods11", "chips")
    os.makedirs(chip_dir, exist_ok=True)

    X_list: list[list[float]] = []
    y_list: list[float] = []
    chip_records: list[dict] = []
    ok_count = 0

    for i, chip_id in enumerate(selected):
        s1_url = f"{_GCS_BASE}/{_S1_PREFIX}{chip_id}_S1Hand.tif"
        label_url = f"{_GCS_BASE}/{_LABEL_PREFIX}{chip_id}_LabelHand.tif"
        s1_path = os.path.join(chip_dir, f"{chip_id}_S1Hand.tif")
        label_path = os.path.join(chip_dir, f"{chip_id}_LabelHand.tif")

        if not _download(s1_url, s1_path) or not _download(label_url, label_path):
            print(f"  [{i+1}/{len(selected)}] {chip_id}: download FAILED, skipping")
            continue

        result = _extract_features(s1_path, label_path)
        if result is None:
            print(f"  [{i+1}/{len(selected)}] {chip_id}: feature extraction FAILED")
            continue

        X_row, y_val = result
        X_list.append(X_row)
        y_list.append(y_val)
        chip_records.append({
            "chip_id": chip_id,
            "event": chip_id.split("_")[0],
            "s1_sha256": _sha256(s1_path),
            "label_sha256": _sha256(label_path),
            "s1_size_bytes": os.path.getsize(s1_path),
            "label_size_bytes": os.path.getsize(label_path),
        })
        ok_count += 1
        print(f"  [{i+1}/{len(selected)}] {chip_id}: y={y_val:.4f}")
        time.sleep(_REQUEST_DELAY)

    if ok_count < 10:
        print(f"\nWARNING: only {ok_count} chips extracted (need >=10 for calibration)")
        return {"dataset": "sen1floods11", "status": "insufficient", "n_chips": ok_count}

    X = np.array(X_list, dtype=float)
    y = np.array(y_list, dtype=float)
    npz_dir = os.path.join(out_dir, "sen1floods11")
    np.save(os.path.join(npz_dir, "X.npy"), X)
    np.save(os.path.join(npz_dir, "y.npy"), y)

    print(f"\nSaved {ok_count} chips: X{X.shape} y{y.shape}")
    print(f"  y range: [{y.min():.4f}, {y.max():.4f}], mean={y.mean():.4f}")

    return {
        "dataset": "sen1floods11",
        "status": "ok",
        "n_chips": ok_count,
        "n_events": len(set(c["event"] for c in chip_records)),
        "features": ["mean_vv", "mean_vh", "vv_vh_diff", "std_vv", "std_vh"],
        "target": "water_fraction",
        "X_shape": list(X.shape),
        "y_shape": list(y.shape),
        "y_min": float(y.min()),
        "y_max": float(y.max()),
        "y_mean": float(y.mean()),
        "chips": chip_records,
    }


def download_xbd(out_dir: str) -> dict:
    """xBD — registration-gated, document and skip."""
    print("\n=== xBD (non-commercial, registration required) ===")
    print("  SKIPPED: xBD requires registration at https://xview2.org/dataset")
    print("  To download: create an account at xView2, agree to the license,")
    print("  then download the xBD dataset manually.")
    return {
        "dataset": "xbd",
        "status": "registration_gated",
        "url": "https://xview2.org/dataset",
        "license": "non-commercial research",
    }


def list_datasets() -> None:
    """Print dataset status table."""
    print(f"{'Dataset':<20} {'License':<25} {'Status':<20} {'Calibrates'}")
    print("-" * 80)
    print(f"{'Sen1Floods11':<20} {'CC BY 4.0':<25} {'direct download':<20} {'sar-flood-mapping'}")
    print(f"{'xBD':<20} {'non-commercial research':<25} {'registration gated':<20} {'building-damage'}")
    print(f"{'UNOSAT':<20} {'per-product':<25} {'registration gated':<20} {'sar-flood-mapping (supp.)'}")
    print(f"{'Copernicus EMS':<20} {'per-product':<25} {'registration gated':<20} {'building-damage (supp.)'}")
    print(f"{'incident-nlp':<20} {'N/A':<25} {'no public data':<20} {'incident-nlp'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download public flood/damage datasets for conformal calibration"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--list", action="store_true", help="show dataset status table")
    group.add_argument("--dataset", type=str, default="all",
                       help="dataset to download (sen1floods11, xbd, all)")
    args = parser.parse_args(argv)

    if args.list:
        list_datasets()
        return 0

    os.makedirs(_OUT_DIR, exist_ok=True)
    manifest: dict = {"datasets": {}, "license_doc": "docs/MODEL_DATA_LICENSING.md"}

    if args.dataset in ("all", "sen1floods11"):
        manifest["datasets"]["sen1floods11"] = download_sen1floods11(_OUT_DIR)
    if args.dataset in ("all", "xbd"):
        manifest["datasets"]["xbd"] = download_xbd(_OUT_DIR)

    manifest_path = os.path.join(_OUT_DIR, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nManifest written to {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
