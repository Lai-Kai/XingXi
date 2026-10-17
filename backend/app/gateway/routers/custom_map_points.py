"""Authenticated map locations selected by administrators."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.gateway.deps import get_current_user_from_request
from app.gateway.map_points_store import MapPointsStore
from app.gateway.routers.map_points import MapPointOut
from deerflow.persistence.engine import get_session_factory

router = APIRouter(prefix="/api/map/custom-points", tags=["map"])


class CreatePointIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)
    lon: float = Field(ge=-180, le=180, allow_inf_nan=False, strict=True)
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False, strict=True)
    request_id: str = Field(min_length=1, max_length=128)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        if re.search(r"[\x00-\x1f\x7f]", value):
            raise ValueError("名称不能包含控制字符")
        return value


def get_store() -> MapPointsStore | None:
    sessions = get_session_factory()
    return MapPointsStore(sessions) if sessions is not None else None


def public_point(row) -> MapPointOut:
    return MapPointOut(
        id=f"custom-point-{row['id']}",
        entity_id=f"custom-place-{row['id']}",
        name=row["name"],
        entity_type="place",
        lon=row["lon"],
        lat=row["lat"],
        confidence="exact",
        basis="管理员在地图上手动选取的坐标。",
        geometry_type="point",
        dynasties=(),
        heritage_status="uncertain",
        access_status="verify_before_visit",
        summary="自建点位，可关联三维模型。",
        address="地图选点",
        evidence=(),
        record_kind="custom",
    )


async def get_custom_points(store=Depends(get_store)) -> list[MapPointOut]:
    return [public_point(row) for row in await store.list()] if store is not None else []


@router.get("", response_model=list[MapPointOut])
async def listing(user=Depends(get_current_user_from_request), points=Depends(get_custom_points)):
    return points


@router.post("", response_model=MapPointOut, status_code=201)
async def create(body: CreatePointIn, user=Depends(get_current_user_from_request), store=Depends(get_store)):
    if user.system_role != "admin":
        raise HTTPException(403, "仅管理员可创建点位")
    if store is None:
        raise HTTPException(503, "点位数据库不可用，请稍后重试")
    try:
        row = await store.create(owner_id=str(user.id), request_id=body.request_id, name=body.name, lon=body.lon, lat=body.lat)
    except ValueError as error:
        raise HTTPException(409, str(error)) from None
    return public_point(row)
