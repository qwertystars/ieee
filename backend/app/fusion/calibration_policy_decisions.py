from __future__ import annotations

from .calibration_policy_types import (
    AbstentionDecision,
    AbstentionInput,
    CalibrationPolicy,
    OutputType,
    ReleaseGateDecision,
)


def policy_for_output_type(output_type: OutputType) -> CalibrationPolicy:
    from .calibration_policy import CALIBRATION_POLICIES

    return {policy.output_type: policy for policy in CALIBRATION_POLICIES}[output_type]


def decide_abstention(evidence: AbstentionInput) -> AbstentionDecision:
    policy = policy_for_output_type(evidence.output_type)
    if not evidence.calibration_available:
        return AbstentionDecision(True, "calibration_unavailable", evidence.output_type)
    if evidence.shift_detected:
        return AbstentionDecision(True, "distribution_shift_detected", evidence.output_type)
    if evidence.confidence is None:
        return AbstentionDecision(True, "confidence_unavailable", evidence.output_type)
    if evidence.confidence < policy.thresholds.confidence_min:
        return AbstentionDecision(True, "confidence_below_threshold", evidence.output_type)
    if evidence.disagreement is not None and evidence.disagreement > policy.thresholds.disagreement_max:
        return AbstentionDecision(True, "ensemble_disagreement_above_threshold", evidence.output_type)
    return AbstentionDecision(False, "", evidence.output_type)


def release_gate(
    policy: CalibrationPolicy,
    calibration_available: bool,
    artifact_version: str | None,
    artifact_sha256: str | None,
) -> ReleaseGateDecision:
    if not calibration_available:
        return ReleaseGateDecision(False, "abstain", "calibration_unavailable")
    if not artifact_version or not artifact_sha256:
        return ReleaseGateDecision(False, "abstain", "calibration_artifact_unavailable")
    if policy.test_tuning_forbidden is not True:
        return ReleaseGateDecision(False, "abstain", "test_tuning_policy_missing")
    return ReleaseGateDecision(True, "available", "")
