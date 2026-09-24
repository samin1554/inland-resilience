"""Pydantic models mirroring contracts/*.schema.json.

The JSON Schemas are the source of truth. If you change a schema, change this file in the same PR;
tests/test_contracts.py fails if the two disagree on any example.
"""

from __future__ import annotations

import uuid
from datetime import date
from enum import StrEnum
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class EvidenceType(StrEnum):
    SATELLITE_DETECTION = "satellite_detection"
    SATELLITE_MEASUREMENT = "satellite_measurement"
    OFFICIAL_PERIMETER = "official_perimeter"
    OFFICIAL_HAZARD_ZONE = "official_hazard_zone"
    WEATHER_OBSERVATION = "weather_observation"
    WEATHER_FORECAST = "weather_forecast"
    WEATHER_ALERT = "weather_alert"
    AIR_QUALITY_OBSERVATION = "air_quality_observation"
    DETERMINISTIC_CALCULATION = "deterministic_calculation"
    AGENT_INFERENCE = "agent_inference"


class JobStatus(StrEnum):
    QUEUED = "queued"
    VALIDATING = "validating"
    RETRIEVING_DATA = "retrieving_data"
    PROCESSING_SATELLITE = "processing_satellite"
    VERIFYING_EVIDENCE = "verifying_evidence"
    GENERATING_REPORT = "generating_report"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


GeometryType = Literal["Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon"]


class Geometry(BaseModel):
    """GeoJSON geometry. Unknown keys from providers are dropped so they can't leak into evidence."""

    model_config = ConfigDict(extra="ignore")

    type: GeometryType
    coordinates: list[Any]


class Evidence(BaseModel):
    """One normalized piece of evidence (contracts/evidence.schema.json)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    job_id: str | None = None
    evidence_type: EvidenceType
    source: str = Field(min_length=1)
    source_record_id: str | None = None
    observed_at: AwareDatetime
    retrieved_at: AwareDatetime
    geometry: Geometry | None
    properties: dict[str, Any]
    quality_flags: list[str]
    limitations: list[str]
    source_url: str

    @staticmethod
    def stable_id(provider_id: str, *parts: object) -> str:
        """Deterministic ID so re-fetching the same record never creates a duplicate (ADR-003)."""
        name = "|".join([provider_id, *(str(p) for p in parts)])
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"inland-resilience:{name}"))

    def with_flag(self, flag: str) -> Evidence:
        if flag in self.quality_flags:
            return self
        return self.model_copy(update={"quality_flags": [*self.quality_flags, flag]})


class DateRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: date
    end: date

    @model_validator(mode="after")
    def _ordered(self) -> DateRange:
        if self.end < self.start:
            raise ValueError("date_range.end must be on or after date_range.start")
        return self


class AreaGeometry(BaseModel):
    type: Literal["Polygon", "MultiPolygon"]
    coordinates: list[Any]


class AnalysisJobMessage(BaseModel):
    """Message on the Redis `jobs` stream (contracts/analysis-job.schema.json)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    job_id: str = Field(min_length=1)
    analysis_type: Literal["historical_fire_impact"]
    question: str = Field(min_length=1, max_length=2000)
    area: AreaGeometry
    date_range: DateRange
    requested_at: AwareDatetime


class JobEvent(BaseModel):
    """Message on the Redis `job-events` stream (contracts/job-event.schema.json)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    job_id: str = Field(min_length=1)
    seq: int = Field(ge=0)
    status: JobStatus
    progress: int = Field(ge=0, le=100)
    stage: str = Field(min_length=1)
    message: str | None = None
    error_code: str | None = None
    at: AwareDatetime
