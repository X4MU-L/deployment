from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class GithubRepositoryRef(BaseModel):
    repository_id: str = Field(min_length=1)
    full_name: str = Field(min_length=1)
    owner_login: str = Field(min_length=1)
    name: str = Field(min_length=1)
    html_url: str = Field(min_length=1)
    default_branch: str | None = None
    private: bool = False


class GithubConnectionCreate(BaseModel):
    account_id: str = Field(min_length=1)
    account_login: str = Field(min_length=1)
    account_name: str | None = None
    installation_id: str | None = None
    selection_mode: str = Field(default="all", pattern="^(all|selected)$")
    selected_repository_ids: list[str] = Field(default_factory=list)


class GithubConnectionResponse(BaseModel):
    id: str
    account_id: str
    account_login: str
    account_name: str | None = None
    installation_id: str | None = None
    selection_mode: str
    selected_repository_ids: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GithubRepositoryListItem(BaseModel):
    repository_id: str
    full_name: str
    owner_login: str
    name: str
    html_url: str
    default_branch: str | None = None
    private: bool = False
    description: str | None = None


class GithubRepositoryListResponse(BaseModel):
    items: list[GithubRepositoryListItem]
    total: int


class BuildSettings(BaseModel):
    root_directory: str | None = None
    install_command: str | None = None
    build_command: str | None = None
    output_directory: str | None = None
    framework_preset: str | None = None
    package_manager: str | None = None


class GithubProjectImport(BaseModel):
    connection_id: str
    repository: GithubRepositoryListItem
    build_settings: BuildSettings | None = None
    repo_url: str | None = None
