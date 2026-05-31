from datetime import datetime

from pydantic import BaseModel


class DeploymentCreate(BaseModel):
    build_id: str
    environment_id: str
    replicas: int = 1


class DeploymentTransition(BaseModel):
    status: str  # pending | provisioning | healthy | unhealthy | promoted
    error_message: str | None = None


class DeploymentResponse(BaseModel):
    id: str
    build_id: str
    environment_id: str
    status: str
    replicas: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}