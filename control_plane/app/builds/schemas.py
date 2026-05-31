from datetime import datetime

from pydantic import BaseModel


class BuildCreate(BaseModel):
    project_id: str
    correlation_id: str | None = None  # auto-generated if omitted
    job_type: str = "build"
    source_ref: str | None = None
    commit_sha: str | None = None
    source_snapshot: dict | None = None
    build_config: dict | None = None
    env_snapshot: dict | None = None


class BuildTransition(BaseModel):
    status: str  # queued | running | succeeded | failed | canceled
    artifact_ref: str | None = None
    error_message: str | None = None


class BuildStatusUpdate(BaseModel):
    status: str
    artifact_ref: str | None = None
    error_message: str | None = None


class BuildResponse(BaseModel):
    id: str
    project_id: str
    correlation_id: str
    attempt: int
    job_type: str
    status: str
    source_ref: str | None
    commit_sha: str | None
    source_snapshot: dict | None = None
    build_config: dict | None = None
    env_snapshot: dict | None = None
    artifact_ref: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BuildSettings(BaseModel):
    root_directory: str | None = None
    install_command: str | None = None
    build_command: str | None = None
    output_directory: str | None = None
    framework_preset: str | None = None
    package_manager: str | None = None
