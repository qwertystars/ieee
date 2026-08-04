# Release Governance and Bounded Claims

The release board has four required authorities: security lead, ML lead, operations lead, and incident-command representative. Quorum is all four. A conflict is declared before review; the conflicted member is recused and a named delegate is recorded without reducing quorum.

The release gate keeps requested claim status separate from aggregate audit status. `PASS` is exit 0, `DEFERRED_EXTERNAL` is exit 2, and `FAIL`, `REVOKED`, missing, or expired evidence is exit 1. An aggregate audit may exit 0 only when every operational deferred claim is explicitly listed in `--allow-deferred`; the bounded research package may remain deferred while its machine integrity gate is valid. Neither aggregate result promotes a claim.

Claim prerequisites are exact and independent:

- Research: dataset, license, split, model, calibration.
- Production: security, config, DR, validator, key custody.
- Shadow: operator, baseline, 30-day observation.
- Field: agency, IRB, training, hardware, physical calibration.

No SOTA, production, shadow, or field claim is promoted by fixture replay. Code, data, model, dependency, gate, manifest, or prerequisite hash changes invalidate the release. Expiry and revocation fail closed. Machine replay may document a bounded validation result but cannot satisfy an external prerequisite.

The board checklist covers software and interoperability gates, ML licensing/splits/calibration/baselines, production configuration and disaster recovery, validator availability, telemetry, rollback, incident response, retraining and drift triggers, and recertification on expiry or material change. Rollback is required after a failed gate, revoked attestation, expiry, or drift/calibration breach. The normative board and unsigned deferred attestations are in `evidence/sota/release-governance.json`; no external signature, authority, participant, agency, hardware, IRB, or custody evidence is fabricated.
