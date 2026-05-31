from fastapi import APIRouter

from app.core.dependencies import (
    CurrentUser,
    EnvironmentRepoDep,
    EnvironmentServiceDep,
    ProjectServiceDep,
)
from app.environments.schemas import EnvironmentCreate, EnvironmentResponse

router = APIRouter(prefix="/environments", tags=["environments"])


@router.post("/", response_model=EnvironmentResponse, status_code=201)
async def create_environment(
    body: EnvironmentCreate,
    user: CurrentUser,
    project_svc: ProjectServiceDep,
    repo: EnvironmentRepoDep,
):
    await project_svc.get_project(user.user_id, body.project_id)
    env = await repo.create(body.project_id, body.name, body.env_vars)
    return env


@router.get("/project/{project_id}", response_model=list[EnvironmentResponse])
async def list_environments(project_id: str, user: CurrentUser, svc: EnvironmentServiceDep):
    return await svc.list_by_project(user.user_id, project_id)


@router.get("/{environment_id}", response_model=EnvironmentResponse)
async def get_environment(environment_id: str, user: CurrentUser, svc: EnvironmentServiceDep):
    return await svc.get_environment(user.user_id, environment_id)
