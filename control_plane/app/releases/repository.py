from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AlreadyExistsError, NotFoundError
from app.db.models.release import Release, Route


class ReleaseRepository:
    async def get_release(self, release_id: str) -> Release | None: ...
    async def list_releases(self, environment_id: str) -> list[Release]: ...
    async def create_release(self, project_id: str, environment_id: str, deployment_id: str) -> Release: ...

    async def get_route_by_hostname(self, hostname: str) -> Route | None: ...
    async def list_routes(self, release_id: str) -> list[Route]: ...
    async def create_route(self, hostname: str, release_id: str) -> Route: ...
    async def delete_route(self, route_id: str) -> None: ...

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)


class SqlAlchemyReleaseRepository(ReleaseRepository):
    def __init__(self, db: AsyncSession):
        self._db = db

    # --- Releases ---
    async def get_release(self, release_id: str) -> Release | None:
        return await self._db.get(Release, release_id)

    async def list_releases(self, environment_id: str) -> list[Release]:
        result = await self._db.execute(
            select(Release)
            .where(Release.environment_id == environment_id)
            .order_by(Release.created_at.desc())
        )
        return list(result.scalars().all())

    async def create_release(
        self, project_id: str, environment_id: str, deployment_id: str
    ) -> Release:
        release = Release(
            project_id=project_id,
            environment_id=environment_id,
            deployment_id=deployment_id,
        )
        self._db.add(release)
        await self._db.flush()
        return release

    # --- Routes ---
    async def get_route_by_hostname(self, hostname: str) -> Route | None:
        result = await self._db.execute(select(Route).where(Route.hostname == hostname))
        return result.scalar_one_or_none()

    async def list_routes(self, release_id: str) -> list[Route]:
        result = await self._db.execute(
            select(Route).where(Route.release_id == release_id)
        )
        return list(result.scalars().all())

    async def create_route(self, hostname: str, release_id: str) -> Route:
        existing = await self.get_route_by_hostname(hostname)
        if existing:
            raise AlreadyExistsError("Route", hostname)
        route = Route(hostname=hostname, release_id=release_id)
        self._db.add(route)
        await self._db.flush()
        return route

    async def delete_route(self, route_id: str) -> None:
        route = await self._db.get(Route, route_id)
        if route is None:
            raise NotFoundError("Route", route_id)
        await self._db.delete(route)
        await self._db.flush()