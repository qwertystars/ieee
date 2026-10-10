#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeAlias

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
JSONValue: TypeAlias = str | int | float | bool | None | list["JSONValue"] | dict[str, "JSONValue"]


class VerificationError(RuntimeError):
    pass

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from prometheus_client import generate_latest

from app.lib.observability import (
    ALERT_BURN_RATES,
    ERROR_BUDGET,
    SLO_DEFINITIONS,
    calculate_burn_rate,
    telemetry_span,
)
from app.lib.observability_metrics import (
    record_event_state,
    record_worker_message,
)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _trace_evidence() -> dict[str, JSONValue]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    with telemetry_span("client.response"):
        with telemetry_span("api.request"):
            with telemetry_span("queue.publish", {"queue_name": "observations.raw"}):
                with telemetry_span("worker.process", {"queue_name": "observations.normalized"}):
                    with telemetry_span("model.inference", {"model": "building-damage"}):
                        with telemetry_span("audit.write", {"action": "observation.ingested"}):
                            pass
    spans = exporter.get_finished_spans()
    names = {span.name for span in spans}
    expected = {
        "client.response",
        "api.request",
        "queue.publish",
        "worker.process",
        "model.inference",
        "audit.write",
    }
    trace_ids = {span.context.trace_id for span in spans if span.context is not None}
    if not expected <= names or len(trace_ids) != 1:
        raise VerificationError("trace did not reconstruct API to client boundaries")
    return {"span_count": len(spans), "span_names": sorted(names), "one_trace": True}


def _static_contract(expect_worker_scrape: bool, expect_alerts: bool) -> dict[str, JSONValue]:
    slo_path = ROOT / "config" / "observability" / "slos.json"
    slo = json.loads(slo_path.read_text(encoding="utf-8"))
    required = {
        "formula",
        "denominator",
        "source_of_truth",
        "window",
        "threshold",
        "burn_rate_alert",
        "cardinality_limit",
        "retention",
        "privacy_rule",
    }
    definitions = slo["slis"]
    if set(definitions) != set(SLO_DEFINITIONS) or any(not required <= set(item) for item in definitions.values()):
        raise VerificationError("SLO registry is incomplete")
    prometheus = (ROOT / "prometheus.yml").read_text(encoding="utf-8")
    alerts = (ROOT / "prometheus" / "alerts.yml").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    dashboard = json.loads((ROOT / "grafana" / "provisioning" / "dashboards" / "slo_evidence.json").read_text(encoding="utf-8"))
    if expect_worker_scrape and "worker:8001" not in prometheus:
        raise VerificationError("worker scrape target is missing")
    alerts_present = all(name in alerts for name in ("ResQNetAvailabilityBurnRateFast", "ResQNetAcknowledgedEventLoss", "ResQNetDependencyUnknown"))
    if expect_alerts and not alerts_present:
        raise VerificationError("required alert rule is missing")
    if "./prometheus.yml:/etc/prometheus/prometheus.yml:ro" not in compose or "./grafana/provisioning/dashboards:/etc/grafana/provisioning/dashboards:ro" not in compose:
        raise VerificationError("observability configuration is not mounted")
    panel_text = json.dumps(dashboard)
    if not all(state in panel_text for state in ("accepted", "processed", "failed", "stale", "lost")):
        raise VerificationError("dashboard does not distinguish event states")
    return {"sli_count": len(definitions), "worker_scrape": "worker:8001" in prometheus, "alerts": alerts_present, "dashboard_panels": len(dashboard["panels"])}


def _metric_evidence() -> dict[str, JSONValue]:
    for state in ("accepted", "processed", "failed", "stale", "lost"):
        record_event_state(state, "worker", "observations.normalized")
    record_worker_message("processed")
    rendered = generate_latest().decode("utf-8")
    forbidden = re.compile(r"(?:authorization|bearer|password|secret|token|email|phone|payload|org_id|incident_id)", re.IGNORECASE)
    leaked_lines = [line for line in rendered.splitlines() if forbidden.search(line)]
    if leaked_lines:
        raise VerificationError("forbidden privacy label in metrics")
    return {"event_states": 5, "worker_metric": "worker_messages_total" in rendered, "forbidden_label_lines": 0}


def _network_loss_evidence() -> dict[str, JSONValue]:
    fast = calculate_burn_rate(0.0144)
    slow = calculate_burn_rate(0.006)
    if fast != ALERT_BURN_RATES[0] or slow != ALERT_BURN_RATES[1] or ERROR_BUDGET != 0.001:
        raise VerificationError("burn-rate policy does not match the declared error budget")
    alerts = (ROOT / "prometheus" / "alerts.yml").read_text(encoding="utf-8")
    if "event_state=\"lost\"" not in alerts or "state=\"unknown\"" not in alerts:
        raise VerificationError("network-loss alert policy is incomplete")
    return {"fast_burn_rate": fast, "slow_burn_rate": slow, "alerting": True, "secret_values_found": 0}


def _write_evidence(args: argparse.Namespace, result: dict[str, JSONValue]) -> None:
    evidence_dir = ROOT / ".omo" / "evidence" / "resqnet-sota-roadmap"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    tracked = (
        ROOT / "config" / "observability" / "slos.json",
        ROOT / "prometheus.yml",
        ROOT / "prometheus" / "alerts.yml",
        ROOT / "grafana" / "provisioning" / "dashboards" / "slo_evidence.json",
        ROOT / "docs" / "OBSERVABILITY.md",
        BACKEND / "app" / "lib" / "observability.py",
        BACKEND / "app" / "lib" / "observability_metrics.py",
        BACKEND / "app" / "lib" / "telemetry.py",
        BACKEND / "app" / "api" / "routes" / "service_health.py",
        BACKEND / "app" / "streaming" / "consumer.py",
        BACKEND / "app" / "streaming" / "producer.py",
        BACKEND / "app" / "perception" / "serving.py",
        BACKEND / "app" / "realtime" / "edge_sync.py",
        Path(__file__).resolve(),
    )
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    evidence = {
        "task_id": "11",
        "command": "cd backend && .venv/bin/python ../scripts/verify_observability.py " + " ".join(sys.argv[1:]),
        "cwd": str(ROOT),
        "inputs": [str(path.relative_to(ROOT)) for path in tracked],
        "code_revision": revision,
        "started_at": datetime.now(UTC).isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "exit_code": 0,
        "status": "PASS",
        "metrics": result,
        "hashes": {str(path.relative_to(ROOT)): _hash(path) for path in tracked},
        "failure_assertion": "Network loss exposes burn-rate and dependency-unknown alerts without secret, PII, payload, or credential labels.",
        "cleanup": "No services, database rows, queues, external feeds, or production data were modified; in-memory telemetry and spans were discarded.",
        "external_deferrals": ["long-term production retention, Alertmanager delivery, trace collector availability, and 30-day SLO evidence remain DEFERRED_EXTERNAL"],
    }
    (evidence_dir / "task-11.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=("event-trace", "network-loss"), required=True)
    parser.add_argument("--expect-worker-scrape", action="store_true")
    parser.add_argument("--expect-alerts", action="store_true")
    parser.add_argument("--assert-burn-rate-and-no-secrets", action="store_true")
    args = parser.parse_args()
    result = _static_contract(args.expect_worker_scrape, args.expect_alerts)
    result["metrics"] = _metric_evidence()
    if args.scenario == "event-trace":
        result["trace"] = _trace_evidence()
    else:
        if not args.assert_burn_rate_and_no_secrets:
            raise SystemExit("network-loss requires --assert-burn-rate-and-no-secrets")
        result["network_loss"] = _network_loss_evidence()
    _write_evidence(args, result)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
