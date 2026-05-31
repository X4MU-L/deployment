from fastapi import APIRouter

from app.builds.schemas import BuildResponse, BuildTriggerRequest
from app.core.dependencies import (
    BuildServiceDep,
    CurrentUser,
    EnvironmentServiceDep,
    ProjectServiceDep,
)
from app.environments.schemas import EnvironmentResponse
from app.projects.schemas import ProjectCreate, ProjectResponse, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("/", response_model=ProjectResponse, status_code=201)
async def create_project(body: ProjectCreate, user: CurrentUser, svc: ProjectServiceDep):
    return await svc.create_project(user.user_id, body)


@router.get("/", response_model=list[ProjectResponse])
async def list_projects(user: CurrentUser, svc: ProjectServiceDep):
    return await svc.list_projects(user.user_id)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, user: CurrentUser, svc: ProjectServiceDep):
    return await svc.get_project(user.user_id, project_id)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str, body: ProjectUpdate, user: CurrentUser, svc: ProjectServiceDep
):
    return await svc.update_project(user.user_id, project_id, body)


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str, user: CurrentUser, svc: ProjectServiceDep):
    await svc.delete_project(user.user_id, project_id)


@router.get("/{project_id}/environments", response_model=list[EnvironmentResponse])
async def list_project_environments(project_id: str, user: CurrentUser, svc: EnvironmentServiceDep):
    return await svc.list_by_project(user.user_id, project_id)


@router.get("/{project_id}/builds", response_model=list[BuildResponse])
async def list_project_builds(project_id: str, user: CurrentUser, svc: BuildServiceDep):
    return await svc.list_builds(user.user_id, project_id)


@router.post("/{project_id}/builds", response_model=BuildResponse, status_code=201)
async def trigger_build(
    project_id: str,
    body: BuildTriggerRequest,
    user: CurrentUser,
    svc: BuildServiceDep,
):
    return await svc.trigger_build(user.user_id, project_id, body)
