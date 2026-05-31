from datetime import datetime

from pydantic import BaseModel


class EnvironmentCreate(BaseModel):
    project_id: str
    name: str  # production, preview, staging
    env_vars: dict | None = None


class EnvironmentResponse(BaseModel):
    id: str
    project_id: str
    name: str
    env_vars: dict[str, str] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
