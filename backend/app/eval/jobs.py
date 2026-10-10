from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.models.coordination import EvaluationJob

JOB_TTL_MS = 7 * 24 * 60 * 60 * 1000


class EvaluationJobStore:
    def __init__(self, db: Session, ttl_ms: int = JOB_TTL_MS) -> None:
        self.db = db
        self.ttl_ms = ttl_ms

    def create(
        self,
        org_id: str,
        created_by: str,
        job_type: str,
        request_payload: dict[str, Any],
        *,
        job_id: str | None = None,
    ) -> EvaluationJob:
        timestamp = now_ms()
        job = EvaluationJob(
            id=job_id or generate_ulid(),
            org_id=org_id,
            created_by=created_by,
            job_type=job_type,
            status="pending",
            request_payload=request_payload,
            result_payload=None,
            error=None,
            created_at_ms=timestamp,
            updated_at_ms=timestamp,
            expires_at_ms=timestamp + self.ttl_ms,
            claimed=False,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get(self, job_id: str, org_id: str) -> EvaluationJob | None:
        return self.db.execute(
            select(EvaluationJob).where(
                EvaluationJob.id == job_id,
                EvaluationJob.org_id == org_id,
                EvaluationJob.expires_at_ms > now_ms(),
            )
        ).scalar_one_or_none()

    def claim(self, job_id: str, org_id: str) -> EvaluationJob | None:
        job = self.db.execute(
            select(EvaluationJob)
            .where(
                EvaluationJob.id == job_id,
                EvaluationJob.org_id == org_id,
                EvaluationJob.expires_at_ms > now_ms(),
            )
            .with_for_update()
        ).scalar_one_or_none()
        if job is None:
            self.db.rollback()
            return None
        if job.claimed or job.status not in {"pending", "running"}:
            self.db.rollback()
            return None
        job.claimed = True
        job.status = "running"
        job.updated_at_ms = now_ms()
        self.db.commit()
        self.db.refresh(job)
        return job

    def complete(self, job_id: str, org_id: str, result_payload: dict[str, Any]) -> EvaluationJob:
        job = self._required(job_id, org_id)
        job.status = "completed"
        job.result_payload = result_payload
        job.error = None
        job.updated_at_ms = now_ms()
        self.db.commit()
        self.db.refresh(job)
        return job

    def fail(self, job_id: str, org_id: str, error: str) -> EvaluationJob:
        job = self._required(job_id, org_id)
        job.status = "failed"
        job.error = error
        job.updated_at_ms = now_ms()
        self.db.commit()
        self.db.refresh(job)
        return job

    def _required(self, job_id: str, org_id: str) -> EvaluationJob:
        job = self.get(job_id, org_id)
        if job is None:
            raise LookupError(f"evaluation job {job_id} not found")
        return job


def job_response(job: EvaluationJob) -> dict[str, Any]:
    response: dict[str, Any] = {
        "task_id": job.id,
        "status": job.status,
        "created_at": job.created_at_ms,
        "created_by": job.created_by,
    }
    if job.result_payload is not None:
        response.update(job.result_payload)
    if job.error is not None:
        response["error"] = job.error
    return response
