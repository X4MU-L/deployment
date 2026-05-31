from contextlib import asynccontextmanager
import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.celery_builder.tasks import _run_fake_build_task
from app.core.config import settings
from app.core.dependencies import get_db
from app.db.models.audit_event import AuditEvent
from app.db.models.build import Build
from app.db.models.log import LogLine
from app.db.models.project import Project
from app.db.models.release import Release, Route
from app.main import app
from tests.conftest import TestSessionFactory


@pytest.fixture
def e2e_client_factory():
    @asynccontextmanager
    async def _factory(base_url: str):
        previous_override = app.dependency_overrides.get(get_db)

        async def _override_get_db():
            async with TestSessionFactory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        app.dependency_overrides[get_db] = _override_get_db
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url=base_url,
            ) as client:
                yield client
        finally:
            if previous_override is None:
                app.dependency_overrides.pop(get_db, None)
            else:
                app.dependency_overrides[get_db] = previous_override

    return _factory


@pytest.mark.asyncio
async def test_user_can_go_from_login_to_release_with_celery_fake_builder(
    client,
    db_session,
    monkeypatch,
    e2e_client_factory,
    local_artifact_store_root,
):
    previous_override = app.dependency_overrides.get(get_db)

    async def _override_get_db():
        async with TestSessionFactory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    try:
        register = await client.post(
            "/api/v1/auth/register/password",
            json={"email": "e2e@example.com", "password": "secret123"},
        )
        assert register.status_code == 201

        login = await client.post(
            "/api/v1/auth/login/password",
            json={"email": "e2e@example.com", "password": "secret123"},
        )
        assert login.status_code == 200
        client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

        me = await client.get("/api/v1/auth/me")
        assert me.status_code == 200
        user_id = me.json()["user_id"]

        project = await client.post(
            "/api/v1/projects/",
            json={
                "name": "lendsqr-fe-test",
                "repo_url": "https://github.com/X4MU-L/lendsqr-fe-test",
                "build_settings": {
                    "install_command": "npm install",
                    "build_command": "npm run build",
                    "output_directory": "build",
                },
            },
        )
        assert project.status_code == 201
        project_body = project.json()
        project_id = project_body["id"]

        builds = []

        def _fake_enqueue_build(request) -> str:
            builds.append(request.build_id)
            return f"celery-{request.build_id}"

        monkeypatch.setattr(
            "app.core.dependencies._background_builder",
            lambda: type(
                "Builder",
                (),
                {
                    "adapter_name": "celery",
                    "enqueue_build": staticmethod(
                        lambda request: type(
                            "Dispatch",
                            (),
                            {"adapter": "celery", "job_id": _fake_enqueue_build(request)},
                        )()
                    ),
                },
            )(),
        )

        trigger = await client.post(f"/api/v1/projects/{project_id}/builds", json={})
        assert trigger.status_code == 201
        build_body = trigger.json()
        build_id = build_body["id"]
        assert build_body["builder_adapter"] == "celery"
        assert build_body["queue_job_id"] == f"celery-{build_id}"
        assert build_body["planned_release_id"]
        assert build_body["triggered_by_user_id"] == user_id
        assert builds == [build_id]

        monkeypatch.setattr(
            "app.celery_builder.execution.build_control_plane_client", e2e_client_factory
        )
        result = await _run_fake_build_task(
            build_id=build_id,
            base_url="http://test",
            service_token="dev-internal-service-token",
            service_name="fake-builder",
            artifact_bucket="fake-static-artifacts",
        )

        assert result["build"]["status"] == "succeeded"
        assert result["release"]["release"]["build_id"] == build_id

        build_status = await client.get(f"/api/v1/builds/{build_id}")
        assert build_status.status_code == 200
        assert build_status.json()["status"] == "succeeded"

        build_logs = await client.get(f"/api/v1/builds/{build_id}/logs")
        assert build_logs.status_code == 200
        log_text = "\n".join(line["content"] for line in build_logs.json())
        assert "fake-builder: received build" in log_text
        assert "simulated static site build completed" in log_text

        release = await client.get(f"/api/v1/builds/{build_id}/release")
        assert release.status_code == 200
        release_body = release.json()
        artifact_ref = release_body["artifact_ref"]
        manifest_ref = release_body["manifest_ref"]

        routes = await client.get(f"/api/v1/releases/{release_body['id']}/routes")
        assert routes.status_code == 200
        assert routes.json()[0]["hostname"].endswith(f".{settings.apps_base_domain}")
        resolved_route = await client.get(
            "/api/v1/internal/routes/resolve",
            params={"hostname": routes.json()[0]["hostname"]},
            headers={
                "Authorization": "Bearer dev-internal-service-token",
                "X-Service-Name": "routing-worker",
            },
        )
        assert resolved_route.status_code == 200
        resolved_body = resolved_route.json()
        assert resolved_body["static_origin"]["r2_bucket"] == "fake-static-artifacts"
        assert resolved_body["static_origin"]["r2_prefix"] == artifact_ref.removeprefix(
            "r2://fake-static-artifacts/"
        ).rstrip("/")
        assert resolved_body["static_origin"]["manifest_path"] == manifest_ref.removeprefix(
            "r2://fake-static-artifacts/"
        )
        assert resolved_body["static_origin"]["index_document"] == "index.html"

        project_row = (
            await db_session.execute(select(Project).where(Project.id == project_id))
        ).scalar_one()
        build_row = (
            await db_session.execute(select(Build).where(Build.id == build_id))
        ).scalar_one()
        release_row = (
            await db_session.execute(select(Release).where(Release.id == release_body["id"]))
        ).scalar_one()
        route_row = (
            await db_session.execute(select(Route).where(Route.release_id == release_body["id"]))
        ).scalar_one()
        log_rows = (
            (await db_session.execute(select(LogLine).where(LogLine.build_id == build_id)))
            .scalars()
            .all()
        )
        audit_rows = (
            (await db_session.execute(select(AuditEvent).order_by(AuditEvent.created_at)))
            .scalars()
            .all()
        )

        assert project_row.repo_url == "https://github.com/X4MU-L/lendsqr-fe-test"
        assert build_row.builder_adapter == "celery"
        assert build_row.queue_job_id == f"celery-{build_id}"
        assert release_row.build_id == build_id
        assert release_row.id == build_body["planned_release_id"]
        assert route_row.hostname.endswith(f".{settings.apps_base_domain}")
        assert len(log_rows) >= 4
        artifact_key = artifact_ref.removeprefix("r2://fake-static-artifacts/")
        manifest_key = manifest_ref.removeprefix("r2://fake-static-artifacts/")
        artifact_root = Path(local_artifact_store_root) / "fake-static-artifacts" / artifact_key
        manifest_path = Path(local_artifact_store_root) / "fake-static-artifacts" / manifest_key
        assert (artifact_root / "index.html").exists()
        assert any(path.name.startswith("app-") for path in (artifact_root / "assets").iterdir())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["schema"] == "static_release_manifest.v1"
        assert manifest["project_id"] == project_id
        assert manifest["build_id"] == build_id
        assert manifest["release_id"] == release_body["id"]
        assert {asset["path"] for asset in manifest["assets"]} == {
            "index.html",
            f"assets/app-{build_id[:8]}.js",
        }
        assert [row.action for row in audit_rows] == [
            "project.created",
            "build.triggered",
            "build.enqueued",
            "release.activated",
            "build.succeeded",
        ]
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override


@pytest.mark.asyncio
async def test_private_repo_flow_fails_without_release(
    client, db_session, monkeypatch, e2e_client_factory, local_artifact_store_root
):
    previous_override = app.dependency_overrides.get(get_db)

    async def _override_get_db():
        async with TestSessionFactory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    try:
        await client.post(
            "/api/v1/auth/register/password",
            json={"email": "private-e2e@example.com", "password": "secret123"},
        )
        login = await client.post(
            "/api/v1/auth/login/password",
            json={"email": "private-e2e@example.com", "password": "secret123"},
        )
        client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

        project = await client.post(
            "/api/v1/projects/",
            json={
                "name": "private-app",
                "repo_url": "https://github.com/acme/private-app",
                "github_connection_id": "conn_123",
                "source_repository": {
                    "repository_id": "repo_123",
                    "full_name": "acme/private-app",
                    "owner_login": "acme",
                    "name": "private-app",
                    "html_url": "https://github.com/acme/private-app",
                    "default_branch": "main",
                    "private": True,
                },
            },
        )
        project_id = project.json()["id"]

        monkeypatch.setattr(
            "app.core.dependencies._background_builder",
            lambda: type(
                "Builder",
                (),
                {
                    "adapter_name": "celery",
                    "enqueue_build": staticmethod(
                        lambda request: type(
                            "Dispatch",
                            (),
                            {"adapter": "celery", "job_id": f"celery-{request.build_id}"},
                        )()
                    ),
                },
            )(),
        )

        trigger = await client.post(f"/api/v1/projects/{project_id}/builds", json={})
        build_id = trigger.json()["id"]

        monkeypatch.setattr(
            "app.celery_builder.execution.build_control_plane_client", e2e_client_factory
        )
        result = await _run_fake_build_task(
            build_id=build_id,
            base_url="http://test",
            service_token="dev-internal-service-token",
            service_name="fake-builder",
            artifact_bucket="fake-static-artifacts",
        )

        assert result["build"]["status"] == "failed"
        assert result["release"] is None

        missing_release = await client.get(f"/api/v1/builds/{build_id}/release")
        assert missing_release.status_code == 404

        build_row = (
            await db_session.execute(select(Build).where(Build.id == build_id))
        ).scalar_one()
        release_rows = (
            (await db_session.execute(select(Release).where(Release.build_id == build_id)))
            .scalars()
            .all()
        )
        assert build_row.status == "failed"
        assert "private repositories" in (build_row.error_message or "")
        assert release_rows == []
        bucket_root = Path(local_artifact_store_root) / settings.celery_builder_artifact_bucket
        assert not bucket_root.exists()
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override
