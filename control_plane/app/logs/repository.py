from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.log import LogLine


class LogRepository:
    async def append(
        self, build_id: str | None, deployment_id: str | None,
        stream: str, content: str, seq: int,
    ) -> LogLine: ...
    async def get_by_seq(
        self, entity_col: str, entity_id: str, seq: int,
    ) -> LogLine | None: ...
    async def get_since(
        self, entity_col: str, entity_id: str, after_seq: int, limit: int = 500,
    ) -> list[LogLine]: ...
    async def get_max_seq(self, entity_col: str, entity_id: str) -> int | None: ...

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)


class SqlAlchemyLogRepository(LogRepository):
    def __init__(self, db: AsyncSession):
        self._db = db

    async def append(
        self, build_id: str | None, deployment_id: str | None,
        stream: str, content: str, seq: int,
    ) -> LogLine:
        line = LogLine(
            build_id=build_id, deployment_id=deployment_id,
            stream=stream, content=content, seq=seq,
        )
        self._db.add(line)
        await self._db.flush()
        return line

    async def get_by_seq(
        self, entity_col: str, entity_id: str, seq: int,
    ) -> LogLine | None:
        col = getattr(LogLine, entity_col)
        stmt = select(LogLine).where(col == entity_id, LogLine.seq == seq).limit(1)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_since(
        self, entity_col: str, entity_id: str, after_seq: int, limit: int = 500,
    ) -> list[LogLine]:
        col = getattr(LogLine, entity_col)
        stmt = (
            select(LogLine)
            .where(col == entity_id, LogLine.seq > after_seq)
            .order_by(LogLine.seq)
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_max_seq(self, entity_col: str, entity_id: str) -> int | None:
        col = getattr(LogLine, entity_col)
        stmt = (
            select(LogLine.seq)
            .where(col == entity_id)
            .order_by(LogLine.seq.desc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()
