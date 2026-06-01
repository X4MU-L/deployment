from dataclasses import dataclass
from typing import Annotated

import redis.asyncio as redis
from app.artifact_store.base import ArtifactStore
from app.artifact_store.factory import build_artifact_store
from app.audit.repository import AuditRepository, SqlAlchemyAuditRepository
from app.audit.service import AuditService
from app.auth.social_service import SocialOAuthService
from app.auth.tokens import TokenPayload, TokenService, decode_token
from app.auth.user_auth_service import UserAuthService
from app.auth.user_repository import SqlUserAuthRepository, UserAuthRepository
from app.background_builder.base import BackgroundBuilder
from app.background_builder.factory import build_background_builder
from app.builds.repository import BuildRepository, SqlAlchemyBuildRepository
from app.builds.service import BuildService
from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError
from app.db.session import get_db
from app.deployments.repository import DeploymentRepository, SqlAlchemyDeploymentRepository
from app.deployments.service import DeploymentService
from app.environments.repository import EnvironmentRepository, SqlAlchemyEnvironmentRepository
from app.environments.service import EnvironmentService
from app.github.repository import SqlAlchemyGithubConnectionRepository
from app.github.service import GithubService
from app.logs.repository import LogRepository, SqlAlchemyLogRepository
from app.logs.service import LiveLogBroker, LogService
from app.projects.repository import ProjectRepository, SqlAlchemyProjectRepository
from app.projects.service import ProjectService
from app.releases.repository import ReleaseRepository, SqlAlchemyReleaseRepository
from app.releases.service import ReleaseService
from fastapi import Depends, Header, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# ---------------------------------------------------------------------------
# DB session
# ---------------------------------------------------------------------------
DbSession = Annotated[AsyncSession, Depends(get_db)]

# ---------------------------------------------------------------------------
# Repositories
# ---------------------------------------------------------------------------


def _user_repo(db: DbSession) -> UserAuthRepository:
    return SqlUserAuthRepository(db)


def _project_repo(db: DbSession) -> ProjectRepository:
    return SqlAlchemyProjectRepository(db)


def _build_repo(db: DbSession) -> BuildRepository:
    return SqlAlchemyBuildRepository(db)


def _deployment_repo(db: DbSession) -> DeploymentRepository:
    return SqlAlchemyDeploymentRepository(db)


def _environment_repo(db: DbSession) -> EnvironmentRepository:
    return SqlAlchemyEnvironmentRepository(db)


def _release_repo(db: DbSession) -> ReleaseRepository:
    return SqlAlchemyReleaseRepository(db)


def _log_repo(db: DbSession) -> LogRepository:
    return SqlAlchemyLogRepository(db)


def _audit_repo(db: DbSession) -> AuditRepository:
    return SqlAlchemyAuditRepository(db)


UserRepoDep = Annotated[UserAuthRepository, Depends(_user_repo)]
ProjectRepoDep = Annotated[ProjectRepository, Depends(_project_repo)]
BuildRepoDep = Annotated[BuildRepository, Depends(_build_repo)]
DeploymentRepoDep = Annotated[DeploymentRepository, Depends(_deployment_repo)]
EnvironmentRepoDep = Annotated[EnvironmentRepository, Depends(_environment_repo)]
ReleaseRepoDep = Annotated[ReleaseRepository, Depends(_release_repo)]
LogRepoDep = Annotated[LogRepository, Depends(_log_repo)]
AuditRepoDep = Annotated[AuditRepository, Depends(_audit_repo)]

# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------


def _token_service() -> TokenService:
    return TokenService()


def _user_auth_service(
    repo: UserRepoDep,
) -> UserAuthService:
    return UserAuthService(repo)


def _background_builder() -> BackgroundBuilder:
    return build_background_builder(get_settings())


def _artifact_store() -> ArtifactStore:
    return build_artifact_store(get_settings())


def _deployment_service(repo: DeploymentRepoDep) -> DeploymentService:
    return DeploymentService(repo)


def _environment_service(repo: EnvironmentRepoDep) -> EnvironmentService:
    return EnvironmentService(repo)


def _log_service(repo: LogRepoDep) -> LogService:
    return LogService(repo, _live_log_broker)


def _audit_service(repo: AuditRepoDep) -> AuditService:
    return AuditService(repo)


def _github_service(
    db: DbSession, environment_repo: EnvironmentRepoDep, project_repo: ProjectRepoDep
) -> GithubService:
    repo = SqlAlchemyGithubConnectionRepository(db)
    return GithubService(repo, environment_repo, project_repo)


def _get_social_service() -> SocialOAuthService:
    """Return the process-level social OAuth service."""
    if not hasattr(_get_social_service, "_instance"):
        _get_social_service._instance = SocialOAuthService()  # type: ignore[attr-defined]
    return _get_social_service._instance  # type: ignore[attr-defined]


ArtifectStoreDep = Annotated[ArtifactStore, Depends(_artifact_store)]
BuilderServiceDep = Annotated[BackgroundBuilder, Depends(_background_builder)]


# ---------------------------------------------------------------------------
# Redis client provider
# ---------------------------------------------------------------------------
def _redis_client(request: Request) -> redis.Redis:
    """Return the Redis client attached to the FastAPI `app.state` by the
    application lifespan. This ensures a single client is created at startup
    and closed on shutdown.
    """
    client = getattr(request.app.state, "redis", None)
    if client is None:
        settings = get_settings()
        if not settings.REDIS_URL:
            raise RuntimeError("Redis is not configured")
        client = redis.from_url(settings.REDIS_URL)
        request.app.state.redis = client
    return client


AuditServiceDep = Annotated[AuditService, Depends(_audit_service)]


def _project_service(
    project: ProjectRepoDep, environment: EnvironmentRepoDep, audit: AuditServiceDep
) -> ProjectService:
    return ProjectService(project, environment, audit)


def _release_service(
    release_repo: ReleaseRepoDep, audit: AuditServiceDep, artifact_store: ArtifectStoreDep
) -> ReleaseService:
    return ReleaseService(release_repo, audit, artifact_store)


def _build_service(
    build_repo: BuildRepoDep,
    project_repo: ProjectRepoDep,
    environment_repo: EnvironmentRepoDep,
    audit_service: AuditServiceDep,
    builder: BuilderServiceDep,
) -> BuildService:
    return BuildService(
        build_repo,
        project_repo,
        environment_repo,
        audit_service,
        builder,
    )


TokenServiceDep = Annotated[TokenService, Depends(_token_service)]
UserAuthServiceDep = Annotated[UserAuthService, Depends(_user_auth_service)]

BuildServiceDep = Annotated[BuildService, Depends(_build_service)]
DeploymentServiceDep = Annotated[DeploymentService, Depends(_deployment_service)]
EnvironmentServiceDep = Annotated[EnvironmentService, Depends(_environment_service)]
ReleaseServiceDep = Annotated[ReleaseService, Depends(_release_service)]
LogServiceDep = Annotated[LogService, Depends(_log_service)]


ProjectServiceDep = Annotated[ProjectService, Depends(_project_service)]
GithubServiceDep = Annotated[GithubService, Depends(_github_service)]
SocialOAuthServiceDep = Annotated[SocialOAuthService, Depends(_get_social_service)]
RedisDep = Annotated[redis.Redis, Depends(_redis_client)]

_live_log_broker = LiveLogBroker()
# ---------------------------------------------------------------------------
# Current user (JWT auth guard)
# ---------------------------------------------------------------------------


async def get_current_user(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> TokenPayload:
    """Decode ``Authorization: Bearer <jwt>`` and return the token payload.

    Stateless — verifies the JWT signature only; no database lookup required.
    Raises ``UnauthorizedError`` if the header is absent, malformed, or the
    token is invalid or expired.
    """
    if not authorization:
        raise UnauthorizedError(
            message="Login required. Run: fasttunnel login",
            code="LOGIN_REQUIRED",
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise UnauthorizedError(
            message="Invalid authorization header",
            code="INVALID_AUTH_HEADER",
        )
    try:
        return decode_token(token)
    except ValueError as exc:
        raise UnauthorizedError(message=str(exc), code="INVALID_TOKEN") from exc


CurrentUser = Annotated[TokenPayload, Depends(get_current_user)]


@dataclass(frozen=True)
class ServicePrincipal:
    service_name: str


async def get_current_service(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_service_name: Annotated[str | None, Header(alias="X-Service-Name")] = None,
) -> ServicePrincipal:
    settings = get_settings()
    if not authorization:
        raise UnauthorizedError(
            message="Service authorization required", code="SERVICE_AUTH_REQUIRED"
        )
    scheme, _, token = authorization.partition(" ")
    print(
        f"get_current_service: scheme={scheme}, token={token}, x_service_name={x_service_name} thrown away = {_}"
    )
    if scheme.lower() != "bearer" or not token:
        raise UnauthorizedError(
            message="Invalid authorization header",
            code="INVALID_AUTH_HEADER",
        )
    if token != settings.internal_service_token:
        raise UnauthorizedError(message="Invalid service token", code="INVALID_SERVICE_TOKEN")
    return ServicePrincipal(service_name=x_service_name or "builder")


CurrentService = Annotated[ServicePrincipal, Depends(get_current_service)]
