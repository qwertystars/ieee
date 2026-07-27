#!/usr/bin/env python3
"""Pre-download ML models for offline operation.

Usage:
    python scripts/download_models.py --list       # show all models to pre-cache
    python scripts/download_models.py --download   # download to MinIO

The model catalog is defined in ``app.perception.serving.MODEL_CATALOG``.
``--download`` fetches each model from its ``source_url`` and uploads it to
MinIO at ``r2_key``. After download, models are available offline via the
``ModelServing`` layer without internet access.

Environment variables (MinIO):
    MINIO_ENDPOINT   (default: minio:9000)
    MINIO_ACCESS_KEY (default: minioadmin)
    MINIO_SECRET_KEY (default: minioadmin)
    MINIO_BUCKET      (default: models)

Licensing:
    Models are hosted on HuggingFace under the ``resqnet`` organization.
    Each model's license is documented on its HuggingFace model card:
      - sar-flood-mapping: https://huggingface.co/resqnet/sar-flood-mapping
      - building-damage:    https://huggingface.co/resqnet/building-damage
      - incident-nlp:       https://huggingface.co/resqnet/incident-nlp

    Review and comply with each model's license before deploying in
    production. The download script does not modify model artifacts — it
    fetches them verbatim from their upstream ``source_url`` and uploads
    them to MinIO without transformation.

    ONNX Runtime itself is licensed under the MIT License
    (https://github.com/microsoft/onnxruntime/blob/main/LICENSE).
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.request

# Allow running from repo root or backend dir.
_BACKEND = os.path.join(os.path.dirname(__file__), "..", "backend")
if os.path.isdir(_BACKEND):
    sys.path.insert(0, os.path.abspath(_BACKEND))

from app.perception.serving import MODEL_CATALOG, format_catalog  # noqa: E402


def list_models() -> None:
    """Print the model catalog to stdout."""
    print(format_catalog())
    print(f"\nTotal: {len(MODEL_CATALOG)} model(s)")


def download_models() -> int:
    """Download each model from ``source_url`` and upload to MinIO.

    Returns the number of models successfully uploaded.
    """
    try:
        from minio import Minio
    except ImportError:
        print("ERROR: minio package not installed", file=sys.stderr)
        return 1

    endpoint = os.environ.get("MINIO_ENDPOINT", "minio:9000")
    access_key = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
    secret_key = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
    bucket = os.environ.get("MINIO_BUCKET", "models")
    secure = os.environ.get("MINIO_SECURE", "false").lower() == "true"

    client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
        print(f"created bucket: {bucket}")

    uploaded = 0
    for model in MODEL_CATALOG:
        r2_key = model["r2_key"]
        source_url = model["source_url"]
        name = model["name"]
        print(f"downloading {name} from {source_url} ...")
        try:
            tmp_path = f"/tmp/{os.path.basename(r2_key)}"
            urllib.request.urlretrieve(source_url, tmp_path)
            client.fput_object(bucket, r2_key.split("/", 1)[-1] if "/" in r2_key else r2_key, tmp_path)
            os.remove(tmp_path)
            print(f"  uploaded to {bucket}/{r2_key}")
            uploaded += 1
        except Exception as exc:
            print(f"  FAILED: {exc}", file=sys.stderr)
    print(f"\nDone: {uploaded}/{len(MODEL_CATALOG)} models uploaded")
    return uploaded


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pre-download ML models for offline operation")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="show all models to pre-cache")
    group.add_argument("--download", action="store_true", help="download models to MinIO")
    args = parser.parse_args(argv)

    if args.list:
        list_models()
        return 0
    if args.download:
        count = download_models()
        return 0 if count > 0 else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
