from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AlreadyExistsError, NotFoundError
from app.db.models.release import Release, Route


class ReleaseRepository:
    async def get_release(self, release_id: str) -> Release | None: ...
    async def get_release_for_user(self, release_id: str, user_id: str) -> Release | None: ...
    async def get_release_by_build_for_user(self, build_id: str, user_id: str) -> Release | None: ...
    async def list_releases(self, environment_id: str) -> list[Release]: ...
    async def list_releases_for_user(self, environment_id: str, user_id: str) -> list[Release]: ...
    async def create_release(
        self,
        release_id: str | None,
        project_id: str,
        environment_id: str,
        build_id: str,
        deployment_id: str | None = None,
        artifact_ref: str | None = None,
        manifest_ref: str | None = None,
    ) -> Release: ...

    async def get_route_by_hostname(self, hostname: str) -> Route | None: ...
    async def list_routes(self, release_id: str) -> list[Route]: ...
    async def list_routes_for_user(self, release_id: str, user_id: str) -> list[Route]: ...
    async def create_route(self, hostname: str, release_id: str) -> Route: ...
    async def upsert_route(self, hostname: str, release_id: str) -> Route: ...
    async def delete_route(self, route_id: str) -> None: ...

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)


class SqlAlchemyReleaseRepository(ReleaseRepository):
    def __init__(self, db: AsyncSession):
        self._db = db

    # --- Releases ---
    async def get_release(self, release_id: str) -> Release | None:
        return await self._db.get(Release, release_id)

    async def get_release_for_user(self, release_id: str, user_id: str) -> Release | None:
        from app.db.models.project import Project

        result = await self._db.execute(
            select(Release)
            .join(Project, Project.id == Release.project_id)
            .where(Release.id == release_id, Project.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_release_by_build_for_user(self, build_id: str, user_id: str) -> Release | None:
        from app.db.models.project import Project

        result = await self._db.execute(
            select(Release)
            .join(Project, Project.id == Release.project_id)
            .where(Release.build_id == build_id, Project.user_id == user_id)
            .order_by(Release.created_at.desc())
        )
        return result.scalars().first()

    async def list_releases(self, environment_id: str) -> list[Release]:
        result = await self._db.execute(
            select(Release)
            .where(Release.environment_id == environment_id)
            .order_by(Release.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_releases_for_user(self, environment_id: str, user_id: str) -> list[Release]:
        from app.db.models.project import Project

        result = await self._db.execute(
            select(Release)
            .join(Project, Project.id == Release.project_id)
            .where(Release.environment_id == environment_id, Project.user_id == user_id)
            .order_by(Release.created_at.desc())
        )
        return list(result.scalars().all())

    async def create_release(
        self,
        release_id: str | None,
        project_id: str,
        environment_id: str,
        build_id: str,
        deployment_id: str | None = None,
        artifact_ref: str | None = None,
        manifest_ref: str | None = None,
    ) -> Release:
        release = Release(
            id=release_id,
            project_id=project_id,
            environment_id=environment_id,
            build_id=build_id,
            deployment_id=deployment_id,
            artifact_ref=artifact_ref,
            manifest_ref=manifest_ref,
        )
        self._db.add(release)
        await self._db.flush()
        await self._db.refresh(release)
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

    async def list_routes_for_user(self, release_id: str, user_id: str) -> list[Route]:
        from app.db.models.project import Project

        result = await self._db.execute(
            select(Route)
            .join(Release, Release.id == Route.release_id)
            .join(Project, Project.id == Release.project_id)
            .where(Route.release_id == release_id, Project.user_id == user_id)
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

    async def upsert_route(self, hostname: str, release_id: str) -> Route:
        existing = await self.get_route_by_hostname(hostname)
        if existing is None:
            route = Route(hostname=hostname, release_id=release_id)
            self._db.add(route)
            await self._db.flush()
            await self._db.refresh(route)
            return route
        existing.release_id = release_id
        existing.invalidation_version += 1
        await self._db.flush()
        await self._db.refresh(existing)
        return existing

    async def delete_route(self, route_id: str) -> None:
        route = await self._db.get(Route, route_id)
        if route is None:
            raise NotFoundError("Route", route_id)
        await self._db.delete(route)
        await self._db.flush()
