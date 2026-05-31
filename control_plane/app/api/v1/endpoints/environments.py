from fastapi import APIRouter

from app.core.dependencies import EnvironmentRepoDep
from app.environments.schemas import EnvironmentCreate, EnvironmentResponse

router = APIRouter(prefix="/environments", tags=["environments"])


@router.post("/", response_model=EnvironmentResponse, status_code=201)
async def create_environment(body: EnvironmentCreate, repo: EnvironmentRepoDep):
    env = await repo.create(body.project_id, body.name, body.env_vars)
    return env


@router.get("/project/{project_id}", response_model=list[EnvironmentResponse])
async def list_environments(project_id: str, repo: EnvironmentRepoDep):
    return await repo.list_by_project(project_id)


@router.get("/{environment_id}", response_model=EnvironmentResponse)
async def get_environment(environment_id: str, repo: EnvironmentRepoDep):
    env = await repo.get_by_id(environment_id)
    if env is None:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("Environment", environment_id)
    return env
