from datetime import datetime

from pydantic import BaseModel, model_validator


class BuildLogIngestRequest(BaseModel):
    stream: str = "stdout"
    lines: list[str]
    start_seq: int | None = None


class BuildLogStreamEvent(BaseModel):
    id: str
    seq: int
    stream: str
    content: str
    created_at: datetime


class LogIngestRequest(BaseModel):
    """Builder/runner POSTs log lines."""

    build_id: str | None = None
    deployment_id: str | None = None
    stream: str = "stdout"
    lines: list[str]
    start_seq: int | None = None

    @model_validator(mode="after")
    def validate_target(self) -> "LogIngestRequest":
        if (self.build_id is None) == (self.deployment_id is None):
            raise ValueError("Exactly one of build_id or deployment_id must be provided")
        return self


class LogLineResponse(BaseModel):
    id: str
    build_id: str | None
    deployment_id: str | None
    stream: str
    content: str
    seq: int
    created_at: datetime

    model_config = {"from_attributes": True}
