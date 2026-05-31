from datetime import datetime

from pydantic import BaseModel


class ReleaseCreate(BaseModel):
    project_id: str
    environment_id: str
    build_id: str
    deployment_id: str | None = None
    artifact_ref: str | None = None
    manifest_ref: str | None = None


class ReleaseResponse(BaseModel):
    id: str
    project_id: str
    environment_id: str
    build_id: str
    deployment_id: str | None = None
    artifact_ref: str | None = None
    manifest_ref: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RouteCreate(BaseModel):
    hostname: str
    release_id: str


class RouteResponse(BaseModel):
    id: str
    hostname: str
    release_id: str
    invalidation_version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RouteResolutionResponse(BaseModel):
    hostname: str
    route_kind: str
    project_id: str
    release_id: str
    cache_ttl_seconds: int
    invalidation_version: int
    static_origin: dict
