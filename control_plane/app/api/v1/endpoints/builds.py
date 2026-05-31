import json

from fastapi import APIRouter, Header
from sse_starlette.sse import EventSourceResponse

from app.builds.schemas import BuildResponse
from app.core.dependencies import BuildServiceDep, CurrentUser, LogServiceDep, ReleaseServiceDep
from app.core.exceptions import BadRequestError
from app.logs.schemas import LogLineResponse
from app.releases.schemas import ReleaseResponse

router = APIRouter(prefix="/builds", tags=["builds"])


@router.get("/{build_id}", response_model=BuildResponse)
async def get_build(build_id: str, user: CurrentUser, svc: BuildServiceDep):
    return await svc.get_build(user.user_id, build_id)


@router.get("/{build_id}/release", response_model=ReleaseResponse)
async def get_build_release(build_id: str, user: CurrentUser, svc: ReleaseServiceDep):
    return await svc.get_release_for_build(user.user_id, build_id)


@router.get("/{build_id}/logs", response_model=list[LogLineResponse])
async def get_build_logs(
    build_id: str, user: CurrentUser, build_svc: BuildServiceDep, svc: LogServiceDep
):
    await build_svc.get_build(user.user_id, build_id)
    return await svc.get_history(build_id, "build_id")


@router.get("/{build_id}/logs/stream")
async def stream_build_logs(
    build_id: str,
    user: CurrentUser,
    build_svc: BuildServiceDep,
    svc: LogServiceDep,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    await build_svc.get_build(user.user_id, build_id)
    after_seq = _parse_last_event_id(last_event_id)

    async def event_generator():
        async for entry in svc.stream(build_id, "build_id", last_seq=after_seq):
            yield {"event": "log", "data": json.dumps(entry), "id": str(entry["seq"])}

    return EventSourceResponse(event_generator())


def _parse_last_event_id(last_event_id: str | None) -> int:
    if last_event_id is None:
        return -1
    try:
        return int(last_event_id)
    except ValueError as exc:
        raise BadRequestError(
            "Last-Event-ID must be an integer", code="INVALID_LAST_EVENT_ID"
        ) from exc
