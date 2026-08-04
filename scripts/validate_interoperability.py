"""Validate standards-backed interoperability fixtures without claiming agency trials."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.interoperability_contract import ContractInputError, validate_contracts


def main(argv: list[str] | None = None) -> int:
    """Run the local conformance gate and report its external boundary."""
    parser = argparse.ArgumentParser(description="Validate CAP, OGC API Features, and SensorThings contracts")
    parser.add_argument("--profile", type=Path, default=Path("config/cap-profile-v1.2.yaml"))
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--verify-validator-hashes", action="store_true")
    parser.add_argument("--ogc-classes", default="core,crs,query")
    parser.add_argument("--sensorthings-version", default="1.1")
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = validate_contracts(
            args.fixtures,
            args.profile,
            args.lock,
            offline=args.offline,
            expected_ogc=tuple(part for part in args.ogc_classes.split(",") if part),
            sensorthings_version=args.sensorthings_version,
        )
    except ContractInputError as error:
        print("status=FAIL")
        print(f"machine_conformance=FAIL\nerror={error}")
        return 1
    print(f"status={report.status}")
    print(f"machine_conformance={report.metrics['machine_conformance']}")
    print(f"operational_interoperability={report.metrics['operational_interoperability']}")
    if args.verify_validator_hashes:
        print("validator_hashes=VERIFIED_BEFORE_EXECUTION")
    for finding in report.findings:
        print(f"finding={finding}")
    for reason in report.metrics["deferred_reasons"]:
        print(f"deferred_reason={reason}")
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
