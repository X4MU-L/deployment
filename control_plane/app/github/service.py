from __future__ import annotations

import httpx

from app.core.exceptions import NotFoundError
from app.environments.repository import EnvironmentRepository
from app.github.auth import get_installation_token
from app.github.repository import GithubConnectionRepository
from app.projects.repository import ProjectRepository


class GithubService:
    def __init__(
        self,
        repo: GithubConnectionRepository,
        environment_repo: EnvironmentRepository,
        project_repo: ProjectRepository,
    ):
        self._repo = repo
        self._environment_repo = environment_repo
        self._project_repo = project_repo

    async def create_connection(self, user_id: str, data) -> dict:
        conn = await self._repo.create(
            user_id=user_id,
            account_id=data.account_id,
            account_login=data.account_login,
            account_name=data.account_name,
            installation_id=data.installation_id,
            selection_mode=data.selection_mode,
            selected_repository_ids=data.selected_repository_ids,
        )
        return self._to_dict(conn)

    async def list_connections(self, user_id: str) -> list[dict]:
        conns = await self._repo.list_by_user(user_id)
        return [self._to_dict(c) for c in conns]

    async def get_connection(self, conn_id: str) -> dict:
        conn = await self._repo.get_by_id(conn_id)
        if conn is None:
            raise NotFoundError("GithubConnection", conn_id)
        return self._to_dict(conn)

    async def delete_connection(self, user_id: str, conn_id: str) -> None:
        conn = await self._repo.get_by_id_for_user(conn_id, user_id)
        if conn is None:
            raise NotFoundError("GithubConnection", conn_id)
        await self._repo.delete(conn_id)

    async def list_repositories(
        self, user_id: str, conn_id: str, search: str | None = None
    ) -> dict:
        conn = await self._repo.get_by_id_for_user(conn_id, user_id)
        if conn is None:
            raise NotFoundError("GithubConnection", conn_id)
        if not conn.installation_id:
            raise RuntimeError("Github connection is missing installation_id")

        token = await get_installation_token(conn.installation_id)
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "control-plane",
        }
        params = {"per_page": 100}

        url = "https://api.github.com/installation/repositories"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            body = response.json()

        items: list[dict] = []
        for repo in body.get("repositories", []):
            item = {
                "repository_id": str(repo["id"]),
                "full_name": repo["full_name"],
                "owner_login": repo["owner"]["login"],
                "name": repo["name"],
                "html_url": repo["html_url"],
                "default_branch": repo.get("default_branch"),
                "private": bool(repo.get("private", False)),
                "description": repo.get("description"),
            }
            if search:
                haystack = " ".join(
                    [
                        item["full_name"],
                        item["name"],
                        item["owner_login"],
                        item["description"] or "",
                    ]
                ).lower()
                if search.lower() not in haystack:
                    continue
            items.append(item)

        return {"items": items, "total": body.get("total_count", len(items))}

    async def import_repository(self, data, user_id: str) -> dict:
        conn = await self._repo.get_by_id_for_user(data.connection_id, user_id)
        if conn is None:
            raise NotFoundError("GithubConnection", data.connection_id)

        project = await self._project_repo.create(
            user_id=user_id,
            name=data.repository.full_name.rsplit("/", 1)[-1],
            repo_url=data.repo_url or data.repository.html_url,
            default_branch=data.repository.default_branch,
            runtime_type="static",
            source_provider="github",
            github_connection_id=conn.id,
            source_repository=data.repository.model_dump(),
            build_settings=data.build_settings.model_dump() if data.build_settings else None,
        )
        # type: ignore[attr-defined]
        await self._environment_repo.create(project.id, "production", None)
        return self._project_to_dict(project)

    @staticmethod
    def _project_to_dict(project) -> dict:
        return {
            "id": project.id,
            "name": project.name,
            "repo_url": project.repo_url,
            "default_branch": getattr(project, "default_branch", None),
            "runtime_type": project.runtime_type,
            "source_provider": project.source_provider,
            "github_connection_id": project.github_connection_id,
            "source_repository": project.source_repository,
            "build_settings": project.build_settings,
            "created_at": project.created_at,
            "updated_at": project.updated_at,
        }

    @staticmethod
    def _to_dict(c) -> dict:
        return {
            "id": c.id,
            "user_id": getattr(c, "user_id", None),
            "account_id": c.account_id,
            "account_login": c.account_login,
            "account_name": c.account_name,
            "installation_id": c.installation_id,
            "selection_mode": c.selection_mode,
            "selected_repository_ids": c.selected_repository_ids or [],
            "created_at": c.created_at,
            "updated_at": c.updated_at,
        }
