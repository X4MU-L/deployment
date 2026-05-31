from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models.project import Project as ProjectModel
from app.db.models.user import User


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, payload: dict):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url, headers=None, params=None):
        return _FakeResponse(self._payload)


@pytest.mark.asyncio
async def test_list_github_repos_uses_github_app_token(monkeypatch, client):
    create = await client.post(
        "/api/v1/github/connections",
        json={
            "account_id": "acct_1",
            "account_login": "octocat",
            "account_name": "Octo Cat",
            "installation_id": "inst_1",
            "selection_mode": "all",
            "selected_repository_ids": [],
        },
    )
    assert create.status_code == 201
    connection_id = create.json()["id"]

    async def fake_installation_token(installation_id: str) -> str:
        assert installation_id == "inst_1"
        return "installation-token"

    monkeypatch.setattr("app.github.service.get_installation_token", fake_installation_token)
    monkeypatch.setattr(
        "app.github.service.httpx.AsyncClient",
        lambda timeout=30.0: _FakeAsyncClient(
            {
                "total_count": 2,
                "repositories": [
                    {
                        "id": 101,
                        "full_name": "acme/web-app",
                        "owner": {"login": "acme"},
                        "name": "web-app",
                        "html_url": "https://github.com/acme/web-app",
                        "default_branch": "main",
                        "private": True,
                        "description": "Frontend app",
                    },
                    {
                        "id": 102,
                        "full_name": "acme/api-service",
                        "owner": {"login": "acme"},
                        "name": "api-service",
                        "html_url": "https://github.com/acme/api-service",
                        "default_branch": "main",
                        "private": True,
                        "description": "Backend API",
                    },
                ],
            }
        ),
    )

    resp = await client.get(
        f"/api/v1/github/connections/{connection_id}/repos", params={"search": "web"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 1
    assert body["items"][0]["full_name"] == "acme/web-app"


@pytest.mark.asyncio
async def test_import_github_repository_creates_project_for_user(auth_client, db_session):
    user_row = await db_session.execute(select(User).where(User.email == "test@example.com"))
    user = user_row.scalar_one()

    conn = await auth_client.post(
        "/api/v1/github/connections",
        json={
            "account_id": "acct_2",
            "account_login": "octocat",
            "account_name": "Octo Cat",
            "installation_id": "inst_2",
            "selection_mode": "all",
            "selected_repository_ids": [],
        },
    )
    assert conn.status_code == 201
    connection_id = conn.json()["id"]

    payload = {
        "connection_id": connection_id,
        "repository": {
            "repository_id": "repo_9",
            "full_name": "acme/imported-app",
            "owner_login": "acme",
            "name": "imported-app",
            "html_url": "https://github.com/acme/imported-app",
            "default_branch": "main",
            "private": True,
            "description": "Imported app",
        },
        "build_settings": {
            "root_directory": "apps/web",
            "install_command": "pnpm install",
            "build_command": "pnpm build",
            "output_directory": ".next",
            "framework_preset": "nextjs",
            "package_manager": "pnpm",
        },
    }

    resp = await auth_client.post("/api/v1/github/projects/import", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "imported-app"
    assert body["github_connection_id"] == connection_id
    assert body["source_repository"]["repository_id"] == "repo_9"

    row = await db_session.execute(select(ProjectModel).where(ProjectModel.id == body["id"]))
    project = row.scalar_one()
    assert project.user_id == user.user_id
    assert project.source_repository["full_name"] == "acme/imported-app"
    assert project.build_settings["framework_preset"] == "nextjs"
