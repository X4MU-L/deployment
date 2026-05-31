from app.core.exceptions import NotFoundError
from app.environments.repository import EnvironmentRepository


class EnvironmentService:
    def __init__(self, repo: EnvironmentRepository):
        self._repo = repo

    async def list_by_project(self, user_id: str, project_id: str) -> list[dict]:
        envs = await self._repo.list_by_project_for_user(project_id, user_id)
        return [self._to_dict(env) for env in envs]

    async def get_environment(self, user_id: str, environment_id: str) -> dict:
        env = await self._repo.get_by_id_for_user(environment_id, user_id)
        if env is None:
            raise NotFoundError("Environment", environment_id)
        return self._to_dict(env)

    @staticmethod
    def _to_dict(env) -> dict:
        return {
            "id": env.id,
            "project_id": env.project_id,
            "name": env.name,
            "env_vars": env.env_vars,
            "created_at": env.created_at,
            "updated_at": env.updated_at,
        }
