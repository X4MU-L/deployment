from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.project import Project


class ProjectRepository(ABC):
    @abstractmethod
    async def get_by_id(self, project_id: str) -> Project | None: ...

    @abstractmethod
    async def get_by_id_for_user(self, project_id: str, user_id: str) -> Project | None: ...

    @abstractmethod
    async def list_by_user(self, user_id: str) -> list[Project]: ...

    @abstractmethod
    async def create(
        self,
        user_id: str,
        name: str,
        repo_url: str,
        default_branch: str | None,
        runtime_type: str,
        source_provider: str = "github",
        github_connection_id: str | None = None,
        source_repository: dict[str, Any] | None = None,
        build_settings: dict[str, Any] | None = None,
    ) -> Project: ...

    @abstractmethod
    async def update(self, project_id: str, **fields) -> Project: ...

    @abstractmethod
    async def delete(self, project_id: str) -> None: ...

    @abstractmethod
    async def find_by_github_repo(
        self, github_connection_id: str, full_name: str
    ) -> Project | None: ...

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)


class SqlAlchemyProjectRepository(ProjectRepository):
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_by_id(self, project_id: str) -> Project | None:
        return await self._db.get(Project, project_id)

    async def get_by_id_for_user(self, project_id: str, user_id: str) -> Project | None:
        result = await self._db.execute(
            select(Project).where(Project.id == project_id, Project.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: str) -> list[Project]:
        result = await self._db.execute(
            select(Project).where(Project.user_id == user_id).order_by(Project.created_at)
        )
        return list(result.scalars().all())

    async def create(
        self,
        user_id: str,
        name: str,
        repo_url: str,
        default_branch: str | None,
        runtime_type: str,
        source_provider: str = "github",
        github_connection_id: str | None = None,
        source_repository: dict[str, object] | None = None,
        build_settings: dict[str, object] | None = None,
    ) -> Project:
        project = Project(
            user_id=user_id,
            name=name,
            repo_url=repo_url,
            default_branch=default_branch,
            runtime_type=runtime_type,
            source_provider=source_provider,
            github_connection_id=github_connection_id,
            source_repository=source_repository,
            build_settings=build_settings,
        )
        self._db.add(project)
        await self._db.flush()
        await self._db.refresh(project)
        return project

    async def update(self, project_id: str, **fields) -> Project:
        project = await self.get_by_id(project_id)
        if project is None:
            raise NotFoundError("Project", project_id)
        for key, value in fields.items():
            if value is not None and hasattr(project, key):
                setattr(project, key, value)
        await self._db.flush()
        await self._db.refresh(project)
        return project

    async def delete(self, project_id: str) -> None:
        project = await self.get_by_id(project_id)
        if project is None:
            raise NotFoundError("Project", project_id)
        await self._db.delete(project)
        await self._db.flush()

    async def find_by_github_repo(
        self, github_connection_id: str, full_name: str
    ) -> Project | None:
        # source_repository is stored as JSON containing 'full_name'
        result = await self._db.execute(
            select(Project).where(
                Project.github_connection_id == github_connection_id,
                Project.source_repository["full_name"].as_string() == full_name,
            )
        )
        return result.scalars().first()
