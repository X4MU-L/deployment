from fastapi import APIRouter, Query

from app.builds.schemas import (
    BuildCompleteRequest,
    BuildResponse,
    BuildStatusUpdate,
    BuildTransition,
)
from app.core.dependencies import (
    AuditServiceDep,
    BuildServiceDep,
    CurrentService,
    LogServiceDep,
    ReleaseServiceDep,
)
from app.core.exceptions import BadRequestError
from app.logs.schemas import BuildLogIngestRequest, LogIngestRequest, LogLineResponse
from app.releases.schemas import RouteResolutionResponse

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/builds/{build_id}", response_model=BuildResponse)
async def get_build_for_service(
    build_id: str,
    service: CurrentService,
    svc: BuildServiceDep,
):
    return await svc.get_build_internal(build_id)


@router.post("/builds/{build_id}/status", response_model=BuildResponse)
async def update_build_status(
    build_id: str,
    body: BuildStatusUpdate,
    service: CurrentService,
    svc: BuildServiceDep,
):
    transition = BuildTransition(
        status=body.status,
        artifact_ref=body.artifact_ref,
        error_message=body.error_message,
    )
    return await svc.transition(build_id, transition)


@router.post("/builds/{build_id}/logs", response_model=list[LogLineResponse], status_code=201)
async def ingest_build_logs(
    build_id: str,
    body: BuildLogIngestRequest,
    service: CurrentService,
    svc: LogServiceDep,
):
    return await svc.ingest(
        LogIngestRequest(
            build_id=build_id,
            deployment_id=None,
            stream=body.stream,
            lines=body.lines,
            start_seq=body.start_seq,
        )
    )


@router.post("/builds/{build_id}/complete")
async def complete_build(
    build_id: str,
    body: BuildCompleteRequest,
    service: CurrentService,
    build_svc: BuildServiceDep,
    release_svc: ReleaseServiceDep,
    audit_svc: AuditServiceDep,
):
    build = await build_svc.get_build_internal(build_id)  # noqa: F841
    transition = BuildTransition(
        status=body.status,
        artifact_ref=body.artifact_ref,
        error_message=body.error_message,
    )
    updated = await build_svc.transition(build_id, transition)

    release_info = None
    if body.status == "succeeded":
        if not body.artifact_ref or not body.manifest_ref:
            raise BadRequestError(
                "artifact_ref and manifest_ref are required for succeeded builds",
                code="MISSING_ARTIFACT_FIELDS",
            )
        source_snapshot = updated.get("source_snapshot") or {}
        release_info = await release_svc.activate_static_release(
            actor_type="service",
            actor_user_id=None,
            actor_service=service.service_name,
            project_id=updated["project_id"],
            environment_id=updated["environment_id"],
            build_id=updated["id"],
            artifact_ref=body.artifact_ref,
            manifest_ref=body.manifest_ref,
            project_name=source_snapshot.get("project_name") or updated["project_id"],
        )

    await audit_svc.record(
        actor_type="service",
        actor_service=service.service_name,
        action=f"build.{body.status}",
        project_id=updated["project_id"],
        build_id=updated["id"],
        metadata={"error_message": body.error_message},
    )
    return {"build": updated, "release": release_info}


@router.get("/routes/resolve", response_model=RouteResolutionResponse)
async def resolve_route(
    service: CurrentService,
    svc: ReleaseServiceDep,
    hostname: str = Query(..., min_length=1),
):
    return await svc.resolve_route(hostname)
