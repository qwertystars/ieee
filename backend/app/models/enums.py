"""Python enums for observation, hypothesis, and scenario fields."""

import enum


class SourceType(str, enum.Enum):
    """Provenance of an observation."""

    satellite = "satellite"
    sensor = "sensor"
    drone = "drone"
    social_media = "social_media"
    official_feed = "official_feed"
    citizen_report = "citizen_report"
    model = "model"
    other = "other"


class CorroborationState(str, enum.Enum):
    """Whether an observation has been independently confirmed."""

    uncorroborated = "uncorroborated"
    corroborated = "corroborated"
    contradicted = "contradicted"
    superseded = "superseded"


class AccessPolicy(str, enum.Enum):
    """Visibility classification for an observation."""

    public = "public"
    internal = "internal"
    sensitive = "sensitive"


class HypothesisStatus(str, enum.Enum):
    """Lifecycle state of a hypothesis."""

    active = "active"
    resolved = "resolved"
    superseded = "superseded"


class ScenarioLabel(str, enum.Enum):
    """Best/expected/worst branch label for a scenario."""

    best = "best"
    expected = "expected"
    worst = "worst"


class ScenarioStatus(str, enum.Enum):
    """Execution state of a scenario simulation."""

    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
