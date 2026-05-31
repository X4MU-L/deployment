from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

BUILD_REQUESTED_SCHEMA = "build.requested.v1"


class GitCheckoutMetadata(BaseModel):
    repo_url: str
    source_provider: str | None = None
    repository: dict | None = None
    default_branch: str | None = None
    source_ref: str | None = None
    commit_sha: str | None = None


class StaticBuildSpec(BaseModel):
    kind: str = "static"
    root_directory: str | None = None
    install_command: str | None = None
    build_command: str | None = None
    output_directory: str | None = None
    framework_preset: str | None = None
    package_manager: str | None = None
    env_snapshot: dict | None = None


class ArtifactTarget(BaseModel):
    provider: str = "r2"
    bucket: str
    prefix: str
    manifest_key: str


class BuildRequestedMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_name: str = Field(default=BUILD_REQUESTED_SCHEMA, alias="schema")
    build_id: str
    project_id: str
    environment_id: str | None = None
    release_id: str
    correlation_id: str
    attempt: int = Field(ge=1)
    git_checkout: GitCheckoutMetadata
    build_spec: StaticBuildSpec
    artifact_target: ArtifactTarget
