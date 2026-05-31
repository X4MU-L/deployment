import pytest
from sqlalchemy import select

from app.db.models.project import Project as ProjectModel


@pytest.mark.asyncio
async def test_create_project(auth_client):
    resp = await auth_client.post(
        "/api/v1/projects/",
        json={
            "name": "my-app",
            "repo_url": "https://github.com/example/my-app",
            "runtime_type": "static",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "my-app"
    assert body["repo_url"] == "https://github.com/example/my-app"
    assert "id" in body


@pytest.mark.asyncio
async def test_list_projects(auth_client):
    await auth_client.post(
        "/api/v1/projects/",
        json={
            "name": "p1",
            "repo_url": "https://github.com/ex/p1",
        },
    )
    await auth_client.post(
        "/api/v1/projects/",
        json={
            "name": "p2",
            "repo_url": "https://github.com/ex/p2",
        },
    )
    resp = await auth_client.get("/api/v1/projects/")
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


@pytest.mark.asyncio
async def test_get_project(auth_client):
    create = await auth_client.post(
        "/api/v1/projects/",
        json={
            "name": "get-test",
            "repo_url": "https://github.com/ex/gt",
        },
    )
    project_id = create.json()["id"]
    resp = await auth_client.get(f"/api/v1/projects/{project_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "get-test"


@pytest.mark.asyncio
async def test_update_project(auth_client):
    create = await auth_client.post(
        "/api/v1/projects/",
        json={
            "name": "before",
            "repo_url": "https://github.com/ex/b",
        },
    )
    project_id = create.json()["id"]
    resp = await auth_client.patch(f"/api/v1/projects/{project_id}", json={"name": "after"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "after"


@pytest.mark.asyncio
async def test_delete_project(auth_client):
    create = await auth_client.post(
        "/api/v1/projects/",
        json={
            "name": "deleteme",
            "repo_url": "https://github.com/ex/d",
        },
    )
    project_id = create.json()["id"]
    resp = await auth_client.delete(f"/api/v1/projects/{project_id}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_create_project_with_github_import_metadata(auth_client, db_session):
    payload = {
        "name": "imported-app",
        "repo_url": "https://github.com/acme/imported-app",
        "source_provider": "github",
        "github_connection_id": "conn_123",
        "source_repository": {
            "repository_id": "repo_123",
            "full_name": "acme/imported-app",
            "owner_login": "acme",
            "name": "imported-app",
            "html_url": "https://github.com/acme/imported-app",
            "default_branch": "main",
            "private": True,
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

    resp = await auth_client.post("/api/v1/projects/", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["source_provider"] == "github"
    assert body["github_connection_id"] == "conn_123"
    assert body["source_repository"]["full_name"] == "acme/imported-app"
    assert body["build_settings"]["build_command"] == "pnpm build"

    row = await db_session.execute(select(ProjectModel).where(ProjectModel.id == body["id"]))
    project = row.scalar_one()
    assert project.source_repository["repository_id"] == "repo_123"
    assert project.build_settings["framework_preset"] == "nextjs"
