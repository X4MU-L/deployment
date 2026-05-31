from app.audit.repository import AuditRepository


class AuditService:
    def __init__(self, repo: AuditRepository):
        self._repo = repo

    async def record(
        self,
        *,
        actor_type: str,
        action: str,
        actor_user_id: str | None = None,
        actor_service: str | None = None,
        project_id: str | None = None,
        build_id: str | None = None,
        release_id: str | None = None,
        route_id: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        event = await self._repo.create(
            actor_type=actor_type,
            actor_user_id=actor_user_id,
            actor_service=actor_service,
            action=action,
            project_id=project_id,
            build_id=build_id,
            release_id=release_id,
            route_id=route_id,
            meta=metadata,
        )
        return {"id": event.id}
