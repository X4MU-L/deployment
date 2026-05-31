from app.core.exceptions import InvalidTransitionError, NotFoundError
from app.deployments.repository import DeploymentRepository
from app.deployments.schemas import DeploymentCreate, DeploymentTransition

_DEPLOYMENT_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"provisioning", "unhealthy"},
    "provisioning": {"healthy", "unhealthy"},
    "healthy": {"unhealthy", "promoted"},
    "unhealthy": {"provisioning", "healthy"},  # can recover
    "promoted": set(),
}


class DeploymentService:
    def __init__(self, repo: DeploymentRepository):
        self._repo = repo

    async def create_deployment(self, data: DeploymentCreate) -> dict:
        deployment = await self._repo.create(
            build_id=data.build_id,
            environment_id=data.environment_id,
            replicas=data.replicas,
        )
        return self._to_dict(deployment)

    async def list_deployments(self, environment_id: str) -> list[dict]:
        deployments = await self._repo.list_by_environment(environment_id)
        return [self._to_dict(d) for d in deployments]

    async def get_deployment(self, deployment_id: str) -> dict:
        deployment = await self._repo.get_by_id(deployment_id)
        if deployment is None:
            raise NotFoundError("Deployment", deployment_id)
        return self._to_dict(deployment)

    async def transition(self, deployment_id: str, data: DeploymentTransition) -> dict:
        deployment = await self._repo.get_by_id(deployment_id)
        if deployment is None:
            raise NotFoundError("Deployment", deployment_id)

        allowed = _DEPLOYMENT_TRANSITIONS.get(deployment.status, set())
        if data.status not in allowed:
            raise InvalidTransitionError("Deployment", deployment.status, data.status)

        fields = {"status": data.status}
        if data.error_message:
            fields["error_message"] = data.error_message

        deployment = await self._repo.update(deployment_id, **fields)
        return self._to_dict(deployment)

    @staticmethod
    def _to_dict(d) -> dict:
        return {
            "id": d.id, "build_id": d.build_id, "environment_id": d.environment_id,
            "status": d.status, "replicas": d.replicas, "error_message": d.error_message,
            "created_at": d.created_at, "updated_at": d.updated_at,
        }