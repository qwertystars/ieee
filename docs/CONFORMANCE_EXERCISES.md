# Laboratory and Tabletop Conformance Exercises

Task 24 has two independent gates. The laboratory replay is a deterministic,
machine-only exercise over committed fixtures. The participant tabletop is an
external human exercise and is not executed by this repository.

## Machine replay

Run the normative machine gate from the repository root:

```text
backend/.venv/bin/python scripts/run_exercise.py --scenario tests/fixtures/tabletop-machine-v1.yaml --replay --report evidence/sota/task-24-machine.json
```

The replay covers CAP 1.2/IPAWS 1.0, OGC API Features Core/CRS/Query,
SensorThings 1.1, schema bindings, security fail-closed behavior, role
authorization, authority and dual approval for public warnings, conflicting
reports, offline duplicate and conflict handling, sanitized incident
reconstruction, and tamper detection. Exit `0` means the committed machine
assertions passed. Exit `1` means an unsafe or malformed assertion was found.

The interoperability sub-gate reports local machine conformance separately
from operational interoperability. Missing pinned external validator
artifacts remain `DEFERRED_EXTERNAL`; local fixtures do not establish agency,
production, or operational interoperability.

The unsafe scenario must fail closed:

```text
backend/.venv/bin/python scripts/run_exercise.py --scenario tests/fixtures/tabletop-machine-failures.yaml --replay --assert-fail-closed
```

## Participant tabletop

The external gate is deliberately separate:

```text
backend/.venv/bin/python scripts/run_exercise.py --scenario tests/fixtures/tabletop-external.yaml --prerequisites evidence/sota/prerequisites.json --expect-deferred participant-tabletop
```

It returns exit `2` and `DEFERRED_EXTERNAL` until authorized participants,
agency roles, scores, unresolved-risk severity, after-action owners, and
retest dates exist. The prerequisite register is authoritative and every
record must contain exactly these 13 fields:

```text
id, owner, authority, status, evidence_type, evidence_hash, hash_algorithm,
source_url, recorded_at, expires_at, depends_on, deferred_reason, claim_classes
```

`evidence/sota/tabletop-report.json` is a schema-only deferred artifact. Its
participant fields are null, its SHA-256 hash covers the report with the hash
field set to null, and it cannot be promoted by a machine replay PASS.

This tooling does not execute a field trial, physical hardware test, agency
approval, or participant study.
