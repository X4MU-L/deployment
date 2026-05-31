import json

from fastapi import APIRouter, Header
from sse_starlette.sse import EventSourceResponse

from app.core.dependencies import LogServiceDep
from app.core.exceptions import BadRequestError
from app.logs.schemas import LogIngestRequest, LogLineResponse

router = APIRouter(prefix="/logs", tags=["logs"])


@router.post("/ingest", response_model=list[LogLineResponse], status_code=201)
async def ingest_logs(body: LogIngestRequest, svc: LogServiceDep):
    results = await svc.ingest(body)
    return results


@router.get("/build/{build_id}/stream")
async def stream_build_logs(
    build_id: str,
    svc: LogServiceDep,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    after_seq = _parse_last_event_id(last_event_id)

    async def event_generator():
        async for entry in svc.stream(build_id, "build_id", last_seq=after_seq):
            yield {"event": "log", "data": json.dumps(entry), "id": str(entry["seq"])}

    return EventSourceResponse(event_generator())


@router.get("/deployment/{deployment_id}/stream")
async def stream_deployment_logs(
    deployment_id: str,
    svc: LogServiceDep,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    after_seq = _parse_last_event_id(last_event_id)

    async def event_generator():
        async for entry in svc.stream(deployment_id, "deployment_id", last_seq=after_seq):
            yield {"event": "log", "data": json.dumps(entry), "id": str(entry["seq"])}

    return EventSourceResponse(event_generator())


@router.get("/build/{build_id}", response_model=list[LogLineResponse])
async def get_build_logs(build_id: str, svc: LogServiceDep):
    return await svc.get_history(build_id, "build_id")


@router.get("/deployment/{deployment_id}", response_model=list[LogLineResponse])
async def get_deployment_logs(deployment_id: str, svc: LogServiceDep):
    return await svc.get_history(deployment_id, "deployment_id")


def _parse_last_event_id(last_event_id: str | None) -> int:
    if last_event_id is None:
        return -1
    try:
        return int(last_event_id)
    except ValueError as exc:
        raise BadRequestError(
            "Last-Event-ID must be an integer", code="INVALID_LAST_EVENT_ID"
        ) from exc
