"""Cross-partition leakage checks for the benchmark contract."""

from __future__ import annotations

import math
from datetime import datetime

from scripts.benchmark_contract_types import SPLITS, JsonObject


def partition_records(records: list[JsonObject], split: str) -> list[JsonObject]:
    return [record for record in records if record.get("split") == split]


def _distance_m(first: JsonObject, second: JsonObject) -> float:
    lat1, lon1 = math.radians(float(first["latitude"])), math.radians(float(first["longitude"]))
    lat2, lon2 = math.radians(float(second["latitude"])), math.radians(float(second["longitude"]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    area = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6_371_008.8 * 2 * math.asin(math.sqrt(area))


def check_leakage(records: list[JsonObject], findings: list[str]) -> None:
    partitions = {split: partition_records(records, split) for split in SPLITS}
    required = ("record_id", "acquired_at", "latitude", "longitude")
    if any(
        any(field not in record for field in required)
        or not isinstance(record.get("latitude"), (int, float))
        or not isinstance(record.get("longitude"), (int, float))
        for record in records
    ):
        findings.append("leakage checks require valid record timestamps and coordinates")
        return
    if any(not partitions[split] for split in SPLITS):
        findings.append("leakage checks require non-empty train, calibration, and test partitions")
        return
    timestamps = {
        split: [datetime.fromisoformat(str(record["acquired_at"]).replace("Z", "+00:00")) for record in partitions[split]]
        for split in SPLITS
    }
    cutoff = datetime.fromisoformat("2024-01-01T00:00:00+00:00")
    if max(timestamps["train"]) >= min(timestamps["calibration"]):
        findings.append("temporal leakage: calibration is not ordered after train")
    if max(timestamps["calibration"]) >= min(timestamps["test"]):
        findings.append("temporal leakage: final test is not ordered after calibration")
    for split in ("train", "calibration"):
        for record in partitions[split]:
            if datetime.fromisoformat(str(record["acquired_at"]).replace("Z", "+00:00")) >= cutoff:
                findings.append(f"temporal leakage: {record['record_id']} in {split} is on/after cutoff")
    for record in partitions["test"]:
        if datetime.fromisoformat(str(record["acquired_at"]).replace("Z", "+00:00")) < cutoff:
            findings.append(f"temporal leakage: {record['record_id']} in test is before cutoff")
    pairs = (("train", "calibration"), ("train", "test"), ("calibration", "test"))
    for first, second in pairs:
        for record in partitions[first]:
            for other in partitions[second]:
                if record.get("sha256") == other.get("sha256"):
                    findings.append(f"duplicate leakage: {record['record_id']} and {other['record_id']} share sha256")
                distance = sum(
                    (int(left, 16) ^ int(right, 16)).bit_count()
                    for left, right in zip(str(record.get("phash")), str(other.get("phash")))
                )
                if len(str(record.get("phash"))) == len(str(other.get("phash"))) == 16 and distance <= 4:
                    findings.append(f"near-duplicate leakage: {record['record_id']} and {other['record_id']} pHash distance={distance}")
                if record.get("tile_id") == other.get("tile_id"):
                    findings.append(f"tile-overlap leakage: {record['record_id']} and {other['record_id']} share tile_id")
                if record.get("source_id") == other.get("source_id") or record.get("source_asset_id") == other.get("source_asset_id"):
                    findings.append(f"source-overlap leakage: {record['record_id']} and {other['record_id']} share source")
                if (
                    record.get("incident_id") == other.get("incident_id")
                    or record.get("event_id") == other.get("event_id")
                    or record.get("parent_incident_id") == other.get("parent_incident_id")
                ):
                    findings.append(f"incident-hierarchy leakage: {record['record_id']} and {other['record_id']} share incident hierarchy")
                if _distance_m(record, other) < 10_000:
                    findings.append(f"spatial-buffer leakage: {record['record_id']} and {other['record_id']} are within 10 km")
