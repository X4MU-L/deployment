from typing import Annotated

import redis.asyncio as redis
from fastapi import Depends, Header, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.social_service import SocialOAuthService
from app.auth.tokens import TokenPayload, TokenService, decode_token
from app.auth.user_auth_service import UserAuthService
from app.auth.user_repository import SqlUserAuthRepository, UserAuthRepository
from app.builds.repository import BuildRepository, SqlAlchemyBuildRepository
from app.builds.service import BuildService
from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError
from app.db.session import get_db
from app.deployments.repository import DeploymentRepository, SqlAlchemyDeploymentRepository
from app.deployments.service import DeploymentService
from app.environments.repository import EnvironmentRepository, SqlAlchemyEnvironmentRepository
from app.github.repository import SqlAlchemyGithubConnectionRepository
from app.github.service import GithubService
from app.logs.repository import LogRepository, SqlAlchemyLogRepository
from app.logs.service import LiveLogBroker, LogService
from app.projects.repository import ProjectRepository, SqlAlchemyProjectRepository
from app.projects.service import ProjectService
from app.releases.repository import ReleaseRepository, SqlAlchemyReleaseRepository
from app.releases.service import ReleaseService

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


UserRepoDep = Annotated[UserAuthRepository, Depends(_user_repo)]
ProjectRepoDep = Annotated[ProjectRepository, Depends(_project_repo)]
BuildRepoDep = Annotated[BuildRepository, Depends(_build_repo)]
DeploymentRepoDep = Annotated[DeploymentRepository, Depends(_deployment_repo)]
EnvironmentRepoDep = Annotated[EnvironmentRepository, Depends(_environment_repo)]
ReleaseRepoDep = Annotated[ReleaseRepository, Depends(_release_repo)]
LogRepoDep = Annotated[LogRepository, Depends(_log_repo)]

# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------


def _token_service() -> TokenService:
    return TokenService()


def _user_auth_service(
    repo: UserRepoDep,
) -> UserAuthService:
    return UserAuthService(repo)


def _project_service(repo: ProjectRepoDep) -> ProjectService:
    return ProjectService(repo)


def _build_service(repo: BuildRepoDep) -> BuildService:
    return BuildService(repo)


def _deployment_service(repo: DeploymentRepoDep) -> DeploymentService:
    return DeploymentService(repo)


def _release_service(repo: ReleaseRepoDep) -> ReleaseService:
    return ReleaseService(repo)


def _log_service(repo: LogRepoDep) -> LogService:
    return LogService(repo, _live_log_broker)


def _github_service(db: DbSession) -> GithubService:
    repo = SqlAlchemyGithubConnectionRepository(db)
    return GithubService(repo)


def _get_social_service() -> SocialOAuthService:
    """Return the process-level social OAuth service."""
    if not hasattr(_get_social_service, "_instance"):
        _get_social_service._instance = SocialOAuthService()  # type: ignore[attr-defined]
    return _get_social_service._instance  # type: ignore[attr-defined]


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


TokenServiceDep = Annotated[TokenService, Depends(_token_service)]
UserAuthServiceDep = Annotated[UserAuthService, Depends(_user_auth_service)]
ProjectServiceDep = Annotated[ProjectService, Depends(_project_service)]
BuildServiceDep = Annotated[BuildService, Depends(_build_service)]
DeploymentServiceDep = Annotated[DeploymentService, Depends(_deployment_service)]
ReleaseServiceDep = Annotated[ReleaseService, Depends(_release_service)]
LogServiceDep = Annotated[LogService, Depends(_log_service)]
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
