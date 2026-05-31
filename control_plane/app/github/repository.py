from abc import ABC, abstractmethod

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.github_connection import GithubConnection


class GithubConnectionRepository(ABC):
    @abstractmethod
    async def create(self, **fields) -> GithubConnection: ...

    @abstractmethod
    async def get_by_id(self, conn_id: str) -> GithubConnection | None: ...

    @abstractmethod
    async def get_by_id_for_user(self, conn_id: str, user_id: str) -> GithubConnection | None: ...

    @abstractmethod
    async def get_by_installation_id(self, installation_id: str) -> GithubConnection | None: ...

    @abstractmethod
    async def list_all(self) -> list[GithubConnection]: ...

    @abstractmethod
    async def list_by_user(self, user_id: str) -> list[GithubConnection]: ...

    @abstractmethod
    async def delete(self, conn_id: str) -> None: ...


class SqlAlchemyGithubConnectionRepository(GithubConnectionRepository):
    def __init__(self, db: AsyncSession):
        self._db = db

    async def create(self, **fields) -> GithubConnection:
        conn = GithubConnection(**fields)
        self._db.add(conn)
        await self._db.flush()
        await self._db.refresh(conn)
        return conn

    async def get_by_id(self, conn_id: str) -> GithubConnection | None:
        return await self._db.get(GithubConnection, conn_id)

    async def get_by_id_for_user(self, conn_id: str, user_id: str) -> GithubConnection | None:
        result = await self._db.execute(
            select(GithubConnection).where(
                GithubConnection.id == conn_id, GithubConnection.user_id == user_id
            )
        )
        return result.scalars().first()

    async def get_by_installation_id(self, installation_id: str) -> GithubConnection | None:
        result = await self._db.execute(
            select(GithubConnection).where(GithubConnection.installation_id == str(installation_id))
        )
        return result.scalars().first()

    async def list_all(self) -> list[GithubConnection]:
        result = await self._db.execute(
            select(GithubConnection).order_by(GithubConnection.created_at)
        )
        return list(result.scalars().all())

    async def list_by_user(self, user_id: str) -> list[GithubConnection]:
        result = await self._db.execute(
            select(GithubConnection)
            .where(GithubConnection.user_id == user_id)
            .order_by(GithubConnection.created_at)
        )
        return list(result.scalars().all())

    async def delete(self, conn_id: str) -> None:
        conn = await self.get_by_id(conn_id)
        if conn is None:
            raise NotFoundError("GithubConnection", conn_id)
        await self._db.delete(conn)
        await self._db.flush()
