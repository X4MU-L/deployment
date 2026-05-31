from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.environment import Environment


class EnvironmentRepository:
    async def get_by_id(self, env_id: str) -> Environment | None: ...
    async def list_by_project(self, project_id: str) -> list[Environment]: ...
    async def create(self, project_id: str, name: str, env_vars: dict | None) -> Environment: ...

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)


class SqlAlchemyEnvironmentRepository(EnvironmentRepository):
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_by_id(self, env_id: str) -> Environment | None:
        return await self._db.get(Environment, env_id)

    async def list_by_project(self, project_id: str) -> list[Environment]:
        result = await self._db.execute(
            select(Environment)
            .where(Environment.project_id == project_id)
            .order_by(Environment.name)
        )
        return list(result.scalars().all())

    async def create(self, project_id: str, name: str, env_vars: dict | None) -> Environment:
        env = Environment(
            project_id=project_id,
            name=name,
            env_vars=env_vars,
        )
        self._db.add(env)
        await self._db.flush()
        return env
