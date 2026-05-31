from datetime import datetime

from pydantic import BaseModel


class ReleaseCreate(BaseModel):
    project_id: str
    environment_id: str
    deployment_id: str


class ReleaseResponse(BaseModel):
    id: str
    project_id: str
    environment_id: str
    deployment_id: str
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
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}