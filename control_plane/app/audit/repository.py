from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit_event import AuditEvent


class AuditRepository:
    async def create(self, **fields) -> AuditEvent: ...


class SqlAlchemyAuditRepository(AuditRepository):
    def __init__(self, db: AsyncSession):
        self._db = db

    async def create(self, **fields) -> AuditEvent:
        event = AuditEvent(**fields)
        self._db.add(event)
        await self._db.flush()
        await self._db.refresh(event)
        return event
