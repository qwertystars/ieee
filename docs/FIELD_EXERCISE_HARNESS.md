# Field Exercise Harness

`scripts/run_field_exercise_harness.py` is a read-only machine harness for
Task 26. It exercises a deterministic fixture under degraded connectivity and
does not run a field trial, contact an agency, control hardware, or invoke any
life-safety action.

## Machine gate

The machine fixture fixes and checks thresholds for:

- alert latency p95, packet loss, and duplicate rate;
- offline duration and manual sync-conflict handling;
- authorization failures with zero side effects;
- audit completeness and stale-map critical-action blocking;
- power loss, device loss, intermittent links, and competing incidents; and
- disabled dispatch, public warning, resource commitment, device command, and
  network egress paths.

The event log is sequence ordered, hash chained, and signed with the explicit
fixture-only HMAC-SHA256 key. Replay recomputes the chain and replay digest.
The key is not production device key custody and the result is only a
`field_machine` claim.

```text
backend/.venv/bin/python scripts/run_field_exercise_harness.py --scenario tests/fixtures/field-machine-v1.yaml --replay --report evidence/sota/task-26-machine.json
```

An unsafe fixture exits 1 and prints a remediation for each failed gate:

```text
backend/.venv/bin/python scripts/run_field_exercise_harness.py --scenario tests/fixtures/field-machine-failures.yaml --assert-safe-degradation
```

## External gate

Agency authorization, ethics or IRB approval, training, insurance and safety
review, device inventory, consent, stop authority, field samples, hazard
coverage, blinding, and missing-data rules are external prerequisites. The
13-field prerequisite records are checked against
`evidence/sota/prerequisites.json`. The hashed
`evidence/sota/field-trial-report.json` keeps all unavailable observations
null and records minimums of 100 incidents and 3 hazard types without
fabricating a sample.

```text
backend/.venv/bin/python scripts/run_field_exercise_harness.py --scenario tests/fixtures/field-external.yaml --prerequisites evidence/sota/prerequisites.json --require-agency-hardware --expect-deferred
```

This command exits 2 with `DEFERRED_EXTERNAL`. A machine PASS never satisfies
the external field gate. Failed prerequisite or report-integrity checks exit
1 instead of being converted into a deferred success.
