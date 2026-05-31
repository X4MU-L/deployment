import json

from fastapi import APIRouter, Header
from sse_starlette.sse import EventSourceResponse

from app.builds.schemas import BuildCreate, BuildResponse, BuildStatusUpdate, BuildTransition
from app.core.dependencies import BuildServiceDep, LogServiceDep
from app.core.exceptions import BadRequestError
from app.logs.schemas import BuildLogIngestRequest, LogIngestRequest, LogLineResponse

router = APIRouter(prefix="/builds", tags=["builds"])


@router.post("/", response_model=BuildResponse, status_code=201)
async def create_build(body: BuildCreate, svc: BuildServiceDep):
    return await svc.create_build(body)


@router.get("/{build_id}", response_model=BuildResponse)
async def get_build(build_id: str, svc: BuildServiceDep):
    return await svc.get_build(build_id)


@router.get("/project/{project_id}", response_model=list[BuildResponse])
async def list_builds(project_id: str, svc: BuildServiceDep):
    return await svc.list_builds(project_id)


@router.patch("/{build_id}/transition", response_model=BuildResponse)
async def transition_build(build_id: str, body: BuildTransition, svc: BuildServiceDep):
    return await svc.transition(build_id, body)


@router.post("/{build_id}/status", response_model=BuildResponse)
async def update_build_status(build_id: str, body: BuildStatusUpdate, svc: BuildServiceDep):
    transition = BuildTransition(
        status=body.status,
        artifact_ref=body.artifact_ref,
        error_message=body.error_message,
    )
    return await svc.transition(build_id, transition)


@router.post("/{build_id}/logs", response_model=list[LogLineResponse], status_code=201)
async def ingest_build_logs(build_id: str, body: BuildLogIngestRequest, svc: LogServiceDep):
    return await svc.ingest(
        LogIngestRequest(
            build_id=build_id,
            deployment_id=None,
            stream=body.stream,
            lines=body.lines,
            start_seq=body.start_seq,
        )
    )


@router.get("/{build_id}/logs", response_model=list[LogLineResponse])
async def get_build_logs(build_id: str, svc: LogServiceDep):
    return await svc.get_history(build_id, "build_id")


@router.get("/{build_id}/logs/stream")
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


def _parse_last_event_id(last_event_id: str | None) -> int:
    if last_event_id is None:
        return -1
    try:
        return int(last_event_id)
    except ValueError as exc:
        raise BadRequestError(
            "Last-Event-ID must be an integer", code="INVALID_LAST_EVENT_ID"
        ) from exc
