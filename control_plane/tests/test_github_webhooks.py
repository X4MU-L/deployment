import hashlib
import hmac
import json

import pytest

from app.github.webhooks import verify_github_signature


def test_verify_signature_valid():
    secret = "secret123"
    payload = b'{"foo": "bar"}'
    mac = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    header = f"sha256={mac}"
    assert verify_github_signature(secret, payload, header)


def test_verify_signature_invalid():
    secret = "secret123"
    payload = b'{"foo": "bar"}'
    header = "sha256=deadbeef"
    assert not verify_github_signature(secret, payload, header)


@pytest.mark.asyncio
async def test_webhook_push_creates_build(db_session, client):
    # Create user
    from app.db.models.github_connection import GithubConnection
    from app.db.models.project import Project
    from app.db.models.user import User

    user = User(user_id="u1", email="webhook@example.com")
    db_session.add(user)
    await db_session.flush()

    conn = GithubConnection(
        user_id=user.user_id,
        account_id="acct1",
        account_login="acct",
        installation_id="12345",
        meta={"webhook_secret": "shh"},
    )
    db_session.add(conn)
    await db_session.flush()

    project = Project(
        user_id=user.user_id,
        name="repo",
        repo_url="https://github.com/example/repo",
        github_connection_id=conn.id,
        source_repository={"full_name": "example/repo"},
    )
    db_session.add(project)
    await db_session.flush()

    payload = {
        "installation": {"id": 12345},
        "repository": {"full_name": "example/repo"},
        "ref": "refs/heads/main",
        "after": "deadbeef",
    }
    body = json.dumps(payload).encode()
    mac = hmac.new(b"shh", body, hashlib.sha256).hexdigest()
    sig = f"sha256={mac}"

    resp = await client.post(
        "/api/v1/github/webhooks",
        content=body,
        headers={"X-Hub-Signature-256": sig, "X-GitHub-Event": "push"},
    )
    assert resp.status_code == 200

    # Ensure build created
    from sqlalchemy import select

    from app.db.models.build import Build

    result = await db_session.execute(select(Build).where(Build.project_id == project.id))
    builds = result.scalars().all()
    assert len(builds) == 1
    assert builds[0].commit_sha == "deadbeef"
