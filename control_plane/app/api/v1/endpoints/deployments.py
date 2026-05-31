from fastapi import APIRouter

from app.core.dependencies import DeploymentServiceDep
from app.deployments.schemas import DeploymentCreate, DeploymentResponse, DeploymentTransition

router = APIRouter(prefix="/deployments", tags=["deployments"])


@router.post("/", response_model=DeploymentResponse, status_code=201)
async def create_deployment(body: DeploymentCreate, svc: DeploymentServiceDep):
    return await svc.create_deployment(body)


@router.get("/{deployment_id}", response_model=DeploymentResponse)
async def get_deployment(deployment_id: str, svc: DeploymentServiceDep):
    return await svc.get_deployment(deployment_id)


@router.get("/environment/{environment_id}", response_model=list[DeploymentResponse])
async def list_deployments(environment_id: str, svc: DeploymentServiceDep):
    return await svc.list_deployments(environment_id)


@router.patch("/{deployment_id}/transition", response_model=DeploymentResponse)
async def transition_deployment(
    deployment_id: str, body: DeploymentTransition, svc: DeploymentServiceDep
):
    return await svc.transition(deployment_id, body)
