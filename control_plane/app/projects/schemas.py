from datetime import datetime

from pydantic import BaseModel

from app.builds.schemas import BuildSettings
from app.github.schemas import GithubRepositoryRef


class ProjectCreate(BaseModel):
    name: str
    repo_url: str
    runtime_type: str = "static"
    source_provider: str = "github"
    github_connection_id: str | None = None
    source_repository: GithubRepositoryRef | None = None
    build_settings: BuildSettings | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    repo_url: str | None = None
    runtime_type: str | None = None
    source_provider: str | None = None
    github_connection_id: str | None = None
    source_repository: GithubRepositoryRef | None = None
    build_settings: BuildSettings | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    repo_url: str
    runtime_type: str
    source_provider: str = "github"
    github_connection_id: str | None = None
    source_repository: GithubRepositoryRef | None = None
    build_settings: BuildSettings | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
