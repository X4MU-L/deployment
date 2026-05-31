import re

from app.audit.service import AuditService
from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.releases.repository import ReleaseRepository
from app.releases.schemas import ReleaseCreate, RouteCreate


class ReleaseService:
    def __init__(self, repo: ReleaseRepository, audit: AuditService):
        self._repo = repo
        self._audit = audit

    async def create_release(self, data: ReleaseCreate) -> dict:
        release = await self._repo.create_release(
            project_id=data.project_id,
            environment_id=data.environment_id,
            build_id=data.build_id,
            deployment_id=data.deployment_id,
            artifact_ref=data.artifact_ref,
            manifest_ref=data.manifest_ref,
        )
        return self._release_to_dict(release)

    async def list_releases(self, user_id: str, environment_id: str) -> list[dict]:
        releases = await self._repo.list_releases_for_user(environment_id, user_id)
        return [self._release_to_dict(r) for r in releases]

    async def get_release(self, user_id: str, release_id: str) -> dict:
        release = await self._repo.get_release_for_user(release_id, user_id)
        if release is None:
            raise NotFoundError("Release", release_id)
        return self._release_to_dict(release)

    async def get_release_for_build(self, user_id: str, build_id: str) -> dict:
        release = await self._repo.get_release_by_build_for_user(build_id, user_id)
        if release is None:
            raise NotFoundError("Release", build_id)
        return self._release_to_dict(release)

    # --- Routes ---
    async def create_route(self, data: RouteCreate) -> dict:
        route = await self._repo.create_route(
            hostname=data.hostname, release_id=data.release_id,
        )
        return self._route_to_dict(route)

    async def list_routes(self, user_id: str, release_id: str) -> list[dict]:
        routes = await self._repo.list_routes_for_user(release_id, user_id)
        return [self._route_to_dict(r) for r in routes]

    async def delete_route(self, route_id: str) -> None:
        await self._repo.delete_route(route_id)

    @staticmethod
    def _release_to_dict(r) -> dict:
        return {
            "id": r.id, "project_id": r.project_id,
            "environment_id": r.environment_id, "build_id": r.build_id,
            "deployment_id": r.deployment_id,
            "artifact_ref": getattr(r, "artifact_ref", None),
            "manifest_ref": getattr(r, "manifest_ref", None),
            "created_at": r.created_at, "updated_at": r.updated_at,
        }

    @staticmethod
    def _route_to_dict(r) -> dict:
        return {
            "id": r.id, "hostname": r.hostname, "release_id": r.release_id,
            "invalidation_version": getattr(r, "invalidation_version", 1),
            "created_at": r.created_at, "updated_at": r.updated_at,
        }

    async def activate_static_release(
        self,
        *,
        actor_type: str,
        actor_user_id: str | None,
        actor_service: str | None,
        project_id: str,
        environment_id: str,
        build_id: str,
        artifact_ref: str,
        manifest_ref: str,
        project_name: str,
    ) -> dict:
        release = await self._repo.create_release(
            project_id=project_id,
            environment_id=environment_id,
            build_id=build_id,
            artifact_ref=artifact_ref,
            manifest_ref=manifest_ref,
        )
        hostname = _default_hostname(project_name, project_id)
        route = await self._repo.upsert_route(hostname=hostname, release_id=release.id)
        await self._audit.record(
            actor_type=actor_type,
            actor_user_id=actor_user_id,
            actor_service=actor_service,
            action="release.activated",
            project_id=project_id,
            build_id=build_id,
            release_id=release.id,
            route_id=route.id,
            metadata={"hostname": hostname},
        )
        return {
            "release": self._release_to_dict(release),
            "route": self._route_to_dict(route),
        }

    async def resolve_route(self, hostname: str) -> dict:
        route = await self._repo.get_route_by_hostname(hostname)
        if route is None:
            raise NotFoundError("Route", hostname)
        release = await self._repo.get_release(route.release_id)
        if release is None:
            raise NotFoundError("Release", route.release_id)
        settings = get_settings()
        manifest_path = (release.manifest_ref or "").removeprefix("r2://")
        artifact_path = (release.artifact_ref or "").removeprefix("r2://")
        bucket, _, prefix = artifact_path.partition("/")
        return {
            "hostname": hostname,
            "route_kind": "static",
            "project_id": release.project_id,
            "release_id": release.id,
            "cache_ttl_seconds": settings.route_cache_ttl_seconds,
            "invalidation_version": route.invalidation_version,
            "static_origin": {
                "r2_bucket": bucket,
                "r2_prefix": prefix,
                "manifest_path": manifest_path,
                "index_document": "index.html",
            },
        }


def _default_hostname(project_name: str, project_id: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", project_name.lower()).strip("-") or "app"
    return f"{slug}-{project_id[:8]}.{get_settings().apps_base_domain}"
