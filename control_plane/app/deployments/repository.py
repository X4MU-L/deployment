from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.deployment import Deployment


class DeploymentRepository:
    async def get_by_id(self, deployment_id: str) -> Deployment | None: ...
    async def get_by_id_for_user(self, deployment_id: str, user_id: str) -> Deployment | None: ...
    async def list_by_environment(self, environment_id: str) -> list[Deployment]: ...
    async def list_by_environment_for_user(
        self, environment_id: str, user_id: str
    ) -> list[Deployment]: ...
    async def create(
        self,
        build_id: str,
        environment_id: str,
        replicas: int,
    ) -> Deployment: ...
    async def update(self, deployment_id: str, **fields) -> Deployment: ...

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)


class SqlAlchemyDeploymentRepository(DeploymentRepository):
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_by_id(self, deployment_id: str) -> Deployment | None:
        return await self._db.get(Deployment, deployment_id)

    async def get_by_id_for_user(self, deployment_id: str, user_id: str) -> Deployment | None:
        from app.db.models.environment import Environment
        from app.db.models.project import Project

        result = await self._db.execute(
            select(Deployment)
            .join(Environment, Environment.id == Deployment.environment_id)
            .join(Project, Project.id == Environment.project_id)
            .where(Deployment.id == deployment_id, Project.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_by_environment(self, environment_id: str) -> list[Deployment]:
        result = await self._db.execute(
            select(Deployment)
            .where(Deployment.environment_id == environment_id)
            .order_by(Deployment.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_by_environment_for_user(
        self, environment_id: str, user_id: str
    ) -> list[Deployment]:
        from app.db.models.environment import Environment
        from app.db.models.project import Project

        result = await self._db.execute(
            select(Deployment)
            .join(Environment, Environment.id == Deployment.environment_id)
            .join(Project, Project.id == Environment.project_id)
            .where(Deployment.environment_id == environment_id, Project.user_id == user_id)
            .order_by(Deployment.created_at.desc())
        )
        return list(result.scalars().all())

    async def create(self, build_id: str, environment_id: str, replicas: int) -> Deployment:
        deployment = Deployment(
            build_id=build_id,
            environment_id=environment_id,
            replicas=replicas,
        )
        self._db.add(deployment)
        await self._db.flush()
        await self._db.refresh(deployment)
        return deployment

    async def update(self, deployment_id: str, **fields) -> Deployment:
        deployment = await self.get_by_id(deployment_id)
        if deployment is None:
            raise NotFoundError("Deployment", deployment_id)
        for key, value in fields.items():
            if value is not None and hasattr(deployment, key):
                setattr(deployment, key, value)
        await self._db.flush()
        await self._db.refresh(deployment)
        return deployment
