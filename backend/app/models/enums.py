"""Shared string enums used by models and schemas (DESIGN §4)."""
from __future__ import annotations

import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    emergency_manager = "emergency_manager"
    responder_coordinator = "responder_coordinator"
    field_responder = "field_responder"
    shelter_manager = "shelter_manager"
    viewer = "viewer"


class DisasterType(str, enum.Enum):
    flood = "flood"
    earthquake = "earthquake"
    wildfire = "wildfire"
    storm = "storm"
    other = "other"


class DataSourceType(str, enum.Enum):
    weather = "weather"
    river_gauge = "river_gauge"
    citizen_report = "citizen_report"
    responder_report = "responder_report"
    sensor = "sensor"
    social_media = "social_media"
    satellite = "satellite"
    manual = "manual"


class ObservationType(str, enum.Enum):
    water_level = "water_level"
    rainfall = "rainfall"
    flood_extent = "flood_extent"
    road_condition = "road_condition"
    power_status = "power_status"
    structural_damage = "structural_damage"
    person_in_distress = "person_in_distress"
    weather = "weather"
    river_level = "river_level"
    other = "other"


class ReporterType(str, enum.Enum):
    citizen = "citizen"
    field_responder = "field_responder"
    sensor = "sensor"
    official = "official"


class ReportCategory(str, enum.Enum):
    trapped_person = "trapped_person"
    road_blocked = "road_blocked"
    flooding = "flooding"
    power_outage = "power_outage"
    shelter_need = "shelter_need"
    medical = "medical"
    infrastructure_damage = "infrastructure_damage"
    other = "other"


class Urgency(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class VerificationStatus(str, enum.Enum):
    unverified = "unverified"
    low = "low"
    medium = "medium"
    high = "high"


class PriorityLevel(str, enum.Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    monitoring = "monitoring"
    unknown = "unknown"


class RecommendationType(str, enum.Enum):
    evacuation = "evacuation"
    reroute = "reroute"
    open_shelter = "open_shelter"
    resource_allocation = "resource_allocation"
    rescue = "rescue"
    infrastructure_repair = "infrastructure_repair"
    public_warning = "public_warning"
    other = "other"


class RecommendationStatus(str, enum.Enum):
    draft = "draft"
    reviewed = "reviewed"
    approved = "approved"
    assigned = "assigned"
    in_progress = "in_progress"
    completed = "completed"
    dismissed = "dismissed"


class RoadStatusEnum(str, enum.Enum):
    open = "open"
    blocked = "blocked"
    partially_blocked = "partially_blocked"
    unknown = "unknown"
    dangerous = "dangerous"


class TeamType(str, enum.Enum):
    rescue = "rescue"
    medical = "medical"
    evacuation = "evacuation"
    logistics = "logistics"
    assessment = "assessment"
    fire = "fire"
    police = "police"


class TaskStatus(str, enum.Enum):
    assigned = "assigned"
    accepted = "accepted"
    en_route = "en_route"
    on_site = "on_site"
    completed = "completed"
    blocked = "blocked"
    cancelled = "cancelled"


class ProcessingStatus(str, enum.Enum):
    pending = "pending"
    processed = "processed"
    error = "error"
