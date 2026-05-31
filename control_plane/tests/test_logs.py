import pytest


async def _create_project_and_build(auth_client) -> tuple[str, str]:
    project = await auth_client.post(
        "/api/v1/projects/",
        json={"name": "log-test", "repo_url": "https://github.com/ex/log-test"},
    )
    assert project.status_code == 201
    project_id = project.json()["id"]

    build = await auth_client.post("/api/v1/builds/", json={"project_id": project_id})
    assert build.status_code == 201
    return project_id, build.json()["id"]


@pytest.mark.asyncio
async def test_build_log_ingest_allocates_monotonic_sequences(auth_client):
    _, build_id = await _create_project_and_build(auth_client)

    first = await auth_client.post(
        f"/api/v1/builds/{build_id}/logs",
        json={"stream": "stdout", "lines": ["line 1", "line 2"]},
    )
    assert first.status_code == 201
    assert [line["seq"] for line in first.json()] == [0, 1]

    second = await auth_client.post(
        f"/api/v1/builds/{build_id}/logs",
        json={"stream": "stdout", "lines": ["line 3"]},
    )
    assert second.status_code == 201
    assert [line["seq"] for line in second.json()] == [2]

    history = await auth_client.get(f"/api/v1/builds/{build_id}/logs")
    assert history.status_code == 200
    body = history.json()
    assert [line["seq"] for line in body] == [0, 1, 2]
    assert [line["content"] for line in body] == ["line 1", "line 2", "line 3"]


@pytest.mark.asyncio
async def test_build_log_ingest_is_idempotent_for_retried_chunk(auth_client):
    _, build_id = await _create_project_and_build(auth_client)

    first = await auth_client.post(
        f"/api/v1/builds/{build_id}/logs",
        json={"stream": "stdout", "lines": ["same 1", "same 2"], "start_seq": 0},
    )
    assert first.status_code == 201

    retry = await auth_client.post(
        f"/api/v1/builds/{build_id}/logs",
        json={"stream": "stdout", "lines": ["same 1", "same 2"], "start_seq": 0},
    )
    assert retry.status_code == 201
    assert [line["id"] for line in retry.json()] == [line["id"] for line in first.json()]

    history = await auth_client.get(f"/api/v1/builds/{build_id}/logs")
    assert history.status_code == 200
    assert len(history.json()) == 2


@pytest.mark.asyncio
async def test_build_log_ingest_rejects_conflicting_retry(auth_client):
    _, build_id = await _create_project_and_build(auth_client)

    first = await auth_client.post(
        f"/api/v1/builds/{build_id}/logs",
        json={"stream": "stdout", "lines": ["line 1"], "start_seq": 0},
    )
    assert first.status_code == 201

    conflict = await auth_client.post(
        f"/api/v1/builds/{build_id}/logs",
        json={"stream": "stdout", "lines": ["different line 1"], "start_seq": 0},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "LOG_SEQUENCE_CONFLICT"


@pytest.mark.asyncio
async def test_build_logs_stream_rejects_invalid_last_event_id(auth_client):
    _, build_id = await _create_project_and_build(auth_client)

    response = await auth_client.get(
        f"/api/v1/builds/{build_id}/logs/stream",
        headers={"Last-Event-ID": "not-an-int"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_LAST_EVENT_ID"


@pytest.mark.asyncio
async def test_build_status_endpoint_transitions_build(auth_client):
    _, build_id = await _create_project_and_build(auth_client)

    running = await auth_client.post(
        f"/api/v1/builds/{build_id}/status",
        json={"status": "running"},
    )
    assert running.status_code == 200
    assert running.json()["status"] == "running"

    succeeded = await auth_client.post(
        f"/api/v1/builds/{build_id}/status",
        json={"status": "succeeded", "artifact_ref": "r2://artifacts/projects/p/releases/r"},
    )
    assert succeeded.status_code == 200
    assert succeeded.json()["status"] == "succeeded"
    assert succeeded.json()["artifact_ref"] == "r2://artifacts/projects/p/releases/r"
