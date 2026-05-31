from app.core.exceptions import NotFoundError
from app.releases.repository import ReleaseRepository
from app.releases.schemas import ReleaseCreate, RouteCreate


class ReleaseService:
    def __init__(self, repo: ReleaseRepository):
        self._repo = repo

    async def create_release(self, data: ReleaseCreate) -> dict:
        release = await self._repo.create_release(
            project_id=data.project_id,
            environment_id=data.environment_id,
            deployment_id=data.deployment_id,
        )
        return self._release_to_dict(release)

    async def list_releases(self, environment_id: str) -> list[dict]:
        releases = await self._repo.list_releases(environment_id)
        return [self._release_to_dict(r) for r in releases]

    async def get_release(self, release_id: str) -> dict:
        release = await self._repo.get_release(release_id)
        if release is None:
            raise NotFoundError("Release", release_id)
        return self._release_to_dict(release)

    # --- Routes ---
    async def create_route(self, data: RouteCreate) -> dict:
        route = await self._repo.create_route(
            hostname=data.hostname, release_id=data.release_id,
        )
        return self._route_to_dict(route)

    async def list_routes(self, release_id: str) -> list[dict]:
        routes = await self._repo.list_routes(release_id)
        return [self._route_to_dict(r) for r in routes]

    async def delete_route(self, route_id: str) -> None:
        await self._repo.delete_route(route_id)

    @staticmethod
    def _release_to_dict(r) -> dict:
        return {
            "id": r.id, "project_id": r.project_id,
            "environment_id": r.environment_id, "deployment_id": r.deployment_id,
            "created_at": r.created_at, "updated_at": r.updated_at,
        }

    @staticmethod
    def _route_to_dict(r) -> dict:
        return {
            "id": r.id, "hostname": r.hostname, "release_id": r.release_id,
            "created_at": r.created_at, "updated_at": r.updated_at,
        }