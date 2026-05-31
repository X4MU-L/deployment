from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.environment import Environment


class EnvironmentRepository:
    async def get_by_id(self, env_id: str) -> Environment | None: ...
    async def get_by_id_for_user(self, env_id: str, user_id: str) -> Environment | None: ...
    async def list_by_project(self, project_id: str) -> list[Environment]: ...
    async def list_by_project_for_user(
        self, project_id: str, user_id: str
    ) -> list[Environment]: ...
    async def get_by_project_and_name(self, project_id: str, name: str) -> Environment | None: ...
    async def create(self, project_id: str, name: str, env_vars: dict | None) -> Environment: ...

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)


class SqlAlchemyEnvironmentRepository(EnvironmentRepository):
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_by_id(self, env_id: str) -> Environment | None:
        return await self._db.get(Environment, env_id)

    async def get_by_id_for_user(self, env_id: str, user_id: str) -> Environment | None:
        from app.db.models.project import Project

        result = await self._db.execute(
            select(Environment)
            .join(Project, Project.id == Environment.project_id)
            .where(Environment.id == env_id, Project.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_by_project(self, project_id: str) -> list[Environment]:
        result = await self._db.execute(
            select(Environment)
            .where(Environment.project_id == project_id)
            .order_by(Environment.name)
        )
        return list(result.scalars().all())

    async def list_by_project_for_user(self, project_id: str, user_id: str) -> list[Environment]:
        from app.db.models.project import Project

        result = await self._db.execute(
            select(Environment)
            .join(Project, Project.id == Environment.project_id)
            .where(Environment.project_id == project_id, Project.user_id == user_id)
            .order_by(Environment.name)
        )
        return list(result.scalars().all())

    async def get_by_project_and_name(self, project_id: str, name: str) -> Environment | None:
        result = await self._db.execute(
            select(Environment).where(
                Environment.project_id == project_id, Environment.name == name
            )
        )
        return result.scalar_one_or_none()

    async def create(self, project_id: str, name: str, env_vars: dict | None) -> Environment:
        env = Environment(
            project_id=project_id,
            name=name,
            env_vars=env_vars,
        )
        self._db.add(env)
        await self._db.flush()
        return env
