from urllib.parse import urlparse

from app.audit.service import AuditService
from app.core.exceptions import BadRequestError, NotFoundError
from app.environments.repository import EnvironmentRepository
from app.github.schemas import GithubRepositoryRef
from app.projects.repository import ProjectRepository
from app.projects.schemas import ProjectCreate, ProjectUpdate


class ProjectService:
    def __init__(
        self,
        repo: ProjectRepository,
        environment_repo: EnvironmentRepository,
        audit: AuditService,
    ):
        self._repo = repo
        self._environment_repo = environment_repo
        self._audit = audit

    async def create_project(self, user_id: str, data: ProjectCreate) -> dict:
        runtime_type = data.runtime_type or "static"
        if runtime_type != "static":
            raise BadRequestError(
                "Only static projects are supported in v1",
                code="UNSUPPORTED_RUNTIME_TYPE",
            )

        default_branch = data.default_branch or "main"
        repo_url = _normalize_public_github_repo_url(data.repo_url)
        source_repository = data.source_repository or _repository_ref_from_public_repo(
            repo_url=repo_url,
            default_branch=default_branch,
        )

        project = await self._repo.create(
            user_id=user_id,
            name=data.name,
            repo_url=repo_url,
            default_branch=default_branch,
            runtime_type=runtime_type,
            source_provider=data.source_provider,
            github_connection_id=data.github_connection_id,
            source_repository=source_repository.model_dump(),
            build_settings=data.build_settings.model_dump() if data.build_settings else None,
        )
        await self._environment_repo.create(project.id, "production", None)
        await self._audit.record(
            actor_type="user",
            actor_user_id=user_id,
            action="project.created",
            project_id=project.id,
            metadata={
                "repo_url": project.repo_url,
                "runtime_type": project.runtime_type,
                "default_branch": getattr(project, "default_branch", None),
            },
        )
        return self._to_dict(project)

    async def list_projects(self, user_id: str) -> list[dict]:
        projects = await self._repo.list_by_user(user_id)
        return [self._to_dict(p) for p in projects]

    async def get_project(self, user_id: str, project_id: str) -> dict:
        project = await self._repo.get_by_id_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project", project_id)
        return self._to_dict(project)

    async def update_project(self, user_id: str, project_id: str, data: ProjectUpdate) -> dict:
        project = await self._repo.get_by_id_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project", project_id)
        fields = data.model_dump(exclude_unset=True)
        project = await self._repo.update(project_id, **fields)
        return self._to_dict(project)

    async def delete_project(self, user_id: str, project_id: str) -> None:
        project = await self._repo.get_by_id_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project", project_id)
        await self._repo.delete(project_id)

    @staticmethod
    def _to_dict(p) -> dict:
        return {
            "id": p.id,
            "name": p.name,
            "repo_url": p.repo_url,
            "default_branch": getattr(p, "default_branch", None),
            "runtime_type": p.runtime_type,
            "source_provider": getattr(p, "source_provider", "github"),
            "github_connection_id": getattr(p, "github_connection_id", None),
            "source_repository": getattr(p, "source_repository", None),
            "build_settings": getattr(p, "build_settings", None),
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        }


def _normalize_public_github_repo_url(repo_url: str) -> str:
    parsed = urlparse(repo_url)
    if parsed.scheme != "https" or parsed.netloc != "github.com":
        raise BadRequestError(
            "Manual repo URL intake currently supports only public https://github.com repositories",
            code="UNSUPPORTED_REPO_URL",
        )

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        raise BadRequestError(
            "Repository URL must include both owner and repository name",
            code="INVALID_REPO_URL",
        )

    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not owner or not repo:
        raise BadRequestError(
            "Repository URL must include both owner and repository name",
            code="INVALID_REPO_URL",
        )

    return f"https://github.com/{owner}/{repo}"


def _repository_ref_from_public_repo(repo_url: str, default_branch: str) -> GithubRepositoryRef:
    parts = [part for part in urlparse(repo_url).path.split("/") if part]
    owner, repo = parts[0], parts[1]
    full_name = f"{owner}/{repo}"
    return GithubRepositoryRef(
        repository_id=full_name,
        full_name=full_name,
        owner_login=owner,
        name=repo,
        html_url=repo_url,
        default_branch=default_branch,
        private=False,
    )
