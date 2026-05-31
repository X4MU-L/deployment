import asyncio
from collections.abc import AsyncGenerator

from app.core.exceptions import ConflictError
from app.logs.repository import LogRepository
from app.logs.schemas import LogIngestRequest


class LiveLogBroker:
    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, stream_key: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._queues.setdefault(stream_key, []).append(queue)
        return queue

    def unsubscribe(self, stream_key: str, queue: asyncio.Queue) -> None:
        queues = self._queues.get(stream_key)
        if not queues:
            return
        if queue in queues:
            queues.remove(queue)
        if not queues:
            self._queues.pop(stream_key, None)

    async def publish(self, stream_key: str, entry: dict) -> None:
        for queue in list(self._queues.get(stream_key, [])):
            await queue.put(entry)


class LogService:
    def __init__(self, repo: LogRepository, broker: LiveLogBroker):
        self._repo = repo
        self._broker = broker

    async def ingest(self, data: LogIngestRequest) -> list[dict]:
        entity_id = data.build_id or data.deployment_id
        entity_col = "build_id" if data.build_id else "deployment_id"
        if entity_id is None:
            return []

        stream_key = _stream_key(entity_col, entity_id)
        start_seq = data.start_seq
        if start_seq is None:
            max_seq = await self._repo.get_max_seq(entity_col, entity_id)
            start_seq = 0 if max_seq is None else max_seq + 1

        results = []
        for idx, content in enumerate(data.lines):
            seq = start_seq + idx
            line = await self._repo.get_by_seq(entity_col, entity_id, seq)
            if line is None:
                line = await self._repo.append(
                    build_id=data.build_id,
                    deployment_id=data.deployment_id,
                    stream=data.stream,
                    content=content,
                    seq=seq,
                )
                should_publish = True
            else:
                if line.stream != data.stream or line.content != content:
                    raise ConflictError(
                        "Log sequence already exists with different content",
                        code="LOG_SEQUENCE_CONFLICT",
                    )
                should_publish = False
            entry = {
                "id": line.id,
                "build_id": line.build_id,
                "deployment_id": line.deployment_id,
                "seq": line.seq,
                "stream": line.stream,
                "content": line.content, "created_at": line.created_at.isoformat(),
            }
            results.append(entry)
            if should_publish:
                await self._broker.publish(stream_key, entry)
        return results

    async def stream(
        self, entity_id: str, entity_col: str, last_seq: int = -1
    ) -> AsyncGenerator[dict, None]:
        """Yield historical lines followed by live lines, starting after last_seq."""
        stream_key = _stream_key(entity_col, entity_id)
        queue = self._broker.subscribe(stream_key)
        highest_seq = last_seq
        try:
            lines = await self._repo.get_since(entity_col, entity_id, last_seq)
            for line in lines:
                entry = {
                    "id": line.id,
                    "build_id": line.build_id,
                    "deployment_id": line.deployment_id,
                    "seq": line.seq,
                    "stream": line.stream,
                    "content": line.content, "created_at": line.created_at.isoformat(),
                }
                highest_seq = max(highest_seq, entry["seq"])
                yield entry
            while True:
                entry = await queue.get()
                if entry["seq"] <= highest_seq:
                    continue
                highest_seq = entry["seq"]
                yield entry
        finally:
            self._broker.unsubscribe(stream_key, queue)

    async def get_history(self, entity_id: str, entity_col: str) -> list[dict]:
        lines = await self._repo.get_since(entity_col, entity_id, -1)
        return [
            {
                "id": l.id,
                "build_id": l.build_id,
                "deployment_id": l.deployment_id,
                "seq": l.seq,
                "stream": l.stream,
                "content": l.content, "created_at": l.created_at.isoformat(),
            }
            for l in lines
        ]


def _stream_key(entity_col: str, entity_id: str) -> str:
    return f"{entity_col}:{entity_id}"
