from fastapi import APIRouter

from app.core.dependencies import CurrentUser, ProjectServiceDep
from app.projects.schemas import ProjectCreate, ProjectResponse, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("/", response_model=ProjectResponse, status_code=201)
async def create_project(body: ProjectCreate, user: CurrentUser, svc: ProjectServiceDep):
    return await svc.create_project(user.user_id, body)


@router.get("/", response_model=list[ProjectResponse])
async def list_projects(user: CurrentUser, svc: ProjectServiceDep):
    return await svc.list_projects(user.user_id)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, svc: ProjectServiceDep):
    return await svc.get_project(project_id)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: str, body: ProjectUpdate, svc: ProjectServiceDep):
    return await svc.update_project(project_id, body)


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str, svc: ProjectServiceDep):
    await svc.delete_project(project_id)
