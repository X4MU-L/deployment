from datetime import datetime
from typing import cast

from sqlalchemy import and_, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.build import Build


class BuildRepository:
    async def get_by_id(self, build_id: str) -> Build | None: ...
    async def get_by_id_for_user(self, build_id: str, user_id: str) -> Build | None: ...
    async def list_by_project(self, project_id: str) -> list[Build]: ...
    async def list_by_project_for_user(self, project_id: str, user_id: str) -> list[Build]: ...
    async def create(
        self,
        project_id: str,
        environment_id: str | None,
        triggered_by_user_id: str | None,
        trigger_source: str,
        correlation_id: str,
        attempt: int,
        job_type: str,
        source_ref: str | None = None,
        commit_sha: str | None = None,
        source_snapshot: dict | None = None,
        build_config: dict | None = None,
        env_snapshot: dict | None = None,
        planned_release_id: str | None = None,
    ) -> Build: ...
    async def update(self, build_id: str, **fields) -> Build: ...
    async def claim(
        self,
        build_id: str,
        service_name: str,
        lease_expires_at: datetime,
        now: datetime,
    ) -> tuple[Build, bool]: ...
    async def renew_claim(
        self,
        build_id: str,
        service_name: str,
        lease_expires_at: datetime,
        now: datetime,
    ) -> tuple[Build, bool]: ...

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)


class SqlAlchemyBuildRepository(BuildRepository):
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_by_id(self, build_id: str) -> Build | None:
        return await self._db.get(Build, build_id)

    async def get_by_id_for_user(self, build_id: str, user_id: str) -> Build | None:
        from app.db.models.project import Project

        result = await self._db.execute(
            select(Build)
            .join(Project, Project.id == Build.project_id)
            .where(Build.id == build_id, Project.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_by_project(self, project_id: str) -> list[Build]:
        result = await self._db.execute(
            select(Build).where(Build.project_id == project_id).order_by(Build.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_by_project_for_user(self, project_id: str, user_id: str) -> list[Build]:
        from app.db.models.project import Project

        result = await self._db.execute(
            select(Build)
            .join(Project, Project.id == Build.project_id)
            .where(Build.project_id == project_id, Project.user_id == user_id)
            .order_by(Build.created_at.desc())
        )
        return list(result.scalars().all())

    async def create(
        self,
        project_id: str,
        environment_id: str | None,
        triggered_by_user_id: str | None,
        trigger_source: str,
        correlation_id: str,
        attempt: int,
        job_type: str,
        source_ref: str | None = None,
        commit_sha: str | None = None,
        source_snapshot: dict | None = None,
        build_config: dict | None = None,
        env_snapshot: dict | None = None,
        planned_release_id: str | None = None,
    ) -> Build:
        build = Build(
            project_id=project_id,
            environment_id=environment_id,
            triggered_by_user_id=triggered_by_user_id,
            trigger_source=trigger_source,
            correlation_id=correlation_id,
            attempt=attempt,
            job_type=job_type,
            source_ref=source_ref,
            commit_sha=commit_sha,
            source_snapshot=source_snapshot,
            build_config=build_config,
            env_snapshot=env_snapshot,
            planned_release_id=planned_release_id,
        )
        self._db.add(build)
        await self._db.flush()
        await self._db.refresh(build)
        return build

    async def update(self, build_id: str, **fields) -> Build:
        build = await self.get_by_id(build_id)
        if build is None:
            raise NotFoundError("Build", build_id)
        for key, value in fields.items():
            if hasattr(build, key):
                setattr(build, key, value)
        await self._db.flush()
        await self._db.refresh(build)
        return build

    async def claim(
        self,
        build_id: str,
        service_name: str,
        lease_expires_at: datetime,
        now: datetime,
    ) -> tuple[Build, bool]:
        statement = (
            update(Build)
            .where(
                Build.id == build_id,
                or_(
                    Build.status == "queued",
                    and_(
                        Build.status == "running",
                        or_(
                            Build.claimed_by_service == service_name,
                            Build.claim_expires_at.is_(None),
                            Build.claim_expires_at <= now,
                        ),
                    ),
                ),
            )
            .values(
                status="running",
                claimed_by_service=service_name,
                claim_expires_at=lease_expires_at,
            )
        )
        result = await self._db.execute(statement)
        # Cast the result to CursorResult to expose .rowcount
        cursor_result = cast(CursorResult, result)
        await self._db.flush()

        build = await self.get_by_id(build_id)
        if build is None:
            raise NotFoundError("Build", build_id)
        return build, cursor_result.rowcount > 0

    async def renew_claim(
        self,
        build_id: str,
        service_name: str,
        lease_expires_at: datetime,
        now: datetime,
    ) -> tuple[Build, bool]:
        statement = (
            update(Build)
            .where(
                Build.id == build_id,
                Build.status == "running",
                Build.claimed_by_service == service_name,
                or_(
                    Build.claim_expires_at.is_(None),
                    Build.claim_expires_at > now,
                ),
            )
            .values(
                claim_expires_at=lease_expires_at,
            )
        )
        result = await self._db.execute(statement)
        # Cast the result to CursorResult to expose .rowcount
        cursor_result = cast(CursorResult, result)
        await self._db.flush()
        build = await self.get_by_id(build_id)
        if build is None:
            raise NotFoundError("Build", build_id)
        return build, cursor_result.rowcount > 0
