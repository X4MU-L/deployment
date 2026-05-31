from app.core.exceptions import NotFoundError
from app.projects.repository import ProjectRepository
from app.projects.schemas import ProjectCreate, ProjectUpdate


class ProjectService:
    def __init__(self, repo: ProjectRepository):
        self._repo = repo

    async def create_project(self, user_id: str, data: ProjectCreate) -> dict:
        project = await self._repo.create(
            user_id=user_id,
            name=data.name,
            repo_url=data.repo_url,
            runtime_type=data.runtime_type,
            source_provider=data.source_provider,
            github_connection_id=data.github_connection_id,
            source_repository=data.source_repository.model_dump()
            if data.source_repository
            else None,
            build_settings=data.build_settings.model_dump() if data.build_settings else None,
        )
        return self._to_dict(project)

    async def list_projects(self, user_id: str) -> list[dict]:
        projects = await self._repo.list_by_user(user_id)
        return [self._to_dict(p) for p in projects]

    async def get_project(self, project_id: str) -> dict:
        project = await self._repo.get_by_id(project_id)
        if project is None:
            raise NotFoundError("Project", project_id)
        return self._to_dict(project)

    async def update_project(self, project_id: str, data: ProjectUpdate) -> dict:
        fields = data.model_dump(exclude_unset=True)
        project = await self._repo.update(project_id, **fields)
        return self._to_dict(project)

    async def delete_project(self, project_id: str) -> None:
        await self._repo.delete(project_id)

    @staticmethod
    def _to_dict(p) -> dict:
        return {
            "id": p.id,
            "name": p.name,
            "repo_url": p.repo_url,
            "runtime_type": p.runtime_type,
            "source_provider": getattr(p, "source_provider", "github"),
            "github_connection_id": getattr(p, "github_connection_id", None),
            "source_repository": getattr(p, "source_repository", None),
            "build_settings": getattr(p, "build_settings", None),
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        }
