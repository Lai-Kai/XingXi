from __future__ import annotations

import math
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wu_culture.models import ReviewStatus


class SpatialConfidence(StrEnum):
    EXACT = "exact"
    APPROXIMATE = "approximate"
    SPECULATIVE = "speculative"


class SpatialGeometryType(StrEnum):
    POINT = "point"
    UNCERTAINTY_RADIUS = "uncertainty_radius"
    HISTORICAL_AREA = "historical_area"


class SpatialExtentSource(StrEnum):
    EVIDENCE = "evidence"
    HISTORICAL_MAP = "historical_map"
    EDITORIAL_ESTIMATE = "editorial_estimate"
    CONFIDENCE_DEFAULT = "confidence_default"


DEFAULT_UNCERTAINTY_RADIUS_METERS = {
    SpatialConfidence.APPROXIMATE: 750.0,
    SpatialConfidence.SPECULATIVE: 2500.0,
}
DEFAULT_EXTENT_BASIS = "按空间置信等级生成的可视化包络，不代表历史边界或统计概率。"


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GeoFeature(_M):
    entity_id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    lon: float
    lat: float
    confidence: SpatialConfidence
    basis: str
    geometry_type: SpatialGeometryType = SpatialGeometryType.POINT
    uncertainty_radius_m: float | None = None
    area_coordinates: tuple[tuple[float, float], ...] = ()
    extent_source: SpatialExtentSource | None = None
    extent_basis: str | None = None
    evidence_ids: tuple[str, ...] = ()
    review_status: ReviewStatus = ReviewStatus.PENDING
    release_id: str | None = None

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_point(cls, value):  # noqa: ANN001, ANN206
        if not isinstance(value, dict) or "geometry_type" in value:
            return value
        confidence = SpatialConfidence(value.get("confidence", SpatialConfidence.EXACT))
        migrated = dict(value)
        if confidence is SpatialConfidence.EXACT:
            migrated["geometry_type"] = SpatialGeometryType.POINT
        else:
            migrated.update(
                geometry_type=SpatialGeometryType.UNCERTAINTY_RADIUS,
                uncertainty_radius_m=DEFAULT_UNCERTAINTY_RADIUS_METERS[confidence],
                extent_source=SpatialExtentSource.CONFIDENCE_DEFAULT,
                extent_basis=DEFAULT_EXTENT_BASIS,
            )
        return migrated

    @model_validator(mode="after")
    def validate_feature(self) -> GeoFeature:
        if len(self.evidence_ids) != len(set(self.evidence_ids)) or any(not item.strip() for item in self.evidence_ids):
            raise ValueError("geo evidence IDs must be unique and non-empty")
        coordinates = ((self.lon, self.lat), *self.area_coordinates)
        if any(not (math.isfinite(lon) and math.isfinite(lat)) for lon, lat in coordinates):
            raise ValueError("coordinates must be finite")
        if any(not (-180 <= lon <= 180 and -90 <= lat <= 90) for lon, lat in coordinates):
            raise ValueError("invalid coordinates")
        if self.geometry_type is SpatialGeometryType.POINT:
            if self.confidence is not SpatialConfidence.EXACT:
                raise ValueError("non-exact historical locations require an uncertainty area")
            if self.uncertainty_radius_m is not None or self.area_coordinates:
                raise ValueError("point geometry cannot include an uncertainty extent")
        elif self.geometry_type is SpatialGeometryType.UNCERTAINTY_RADIUS:
            if self.uncertainty_radius_m is None or not 10 <= self.uncertainty_radius_m <= 100_000:
                raise ValueError("uncertainty radius must be between 10 and 100000 metres")
            if self.area_coordinates:
                raise ValueError("radius geometry cannot include polygon coordinates")
        else:
            if self.uncertainty_radius_m is not None:
                raise ValueError("historical area cannot include an uncertainty radius")
            if len(self.area_coordinates) < 4 or self.area_coordinates[0] != self.area_coordinates[-1]:
                raise ValueError("historical area must be a closed polygon with at least four coordinates")
        if self.geometry_type is not SpatialGeometryType.POINT and (self.extent_source is None or not self.extent_basis):
            raise ValueError("uncertainty area requires an extent source and basis")
        return self


class GeoService:
    def __init__(self) -> None:
        self._items: dict[str, GeoFeature] = {}

    def upsert(self, feature: GeoFeature) -> GeoFeature:
        if feature.confidence is SpatialConfidence.SPECULATIVE and not feature.basis:
            raise ValueError("speculative location requires basis")
        self._items[feature.entity_id] = feature
        return feature

    def get(self, entity_id: str) -> GeoFeature | None:
        return self._items.get(entity_id)

    def list(self, *, min_confidence: SpatialConfidence | None = None) -> list[GeoFeature]:
        order = {
            SpatialConfidence.EXACT: 3,
            SpatialConfidence.APPROXIMATE: 2,
            SpatialConfidence.SPECULATIVE: 1,
        }
        rows = sorted(self._items.values(), key=lambda row: row.entity_id)
        if min_confidence is not None:
            rows = [row for row in rows if order[row.confidence] >= order[min_confidence]]
        return rows
