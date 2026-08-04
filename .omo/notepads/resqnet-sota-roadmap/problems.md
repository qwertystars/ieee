# Problems — resqnet-sota-roadmap

Unresolved blockers and technical debt discovered during work on this plan.

_Auto-scaffolded by /start-work. Append new entries below - never overwrite._

---
- Task 4 residual: existing provenance writers in `app/audit/provenance.py` retain their historical chain format; canonical event contracts cover new raw/prediction/decision records without changing that legacy endpoint in this task.
- Task 3 residual: the legacy standalone task-creation and sensing-action endpoints remain outside the new alert-command transition; alert-derived high-consequence tasks are created only by the signed alert `/dispatch` route. A future task should route those independent command surfaces through the same dual-control service.
- Task 3 residual: the frontend cannot safely sign high-consequence commands because no client signing-key contract exists; the UI intentionally exposes only a bounded pending request state and does not call `/dispatch` or claim task creation.
- Task 5 residual: the broker topic's server-side retention policy must still be provisioned as 30 days in deployment/topic administration; application envelopes declare and verify the same retention boundary but cannot change broker configuration at runtime.
