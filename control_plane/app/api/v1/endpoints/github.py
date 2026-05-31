from fastapi import APIRouter, Header, HTTPException, Query, Request

from app.builds.schemas import BuildCreate
from app.core.config import get_settings
from app.core.dependencies import BuildServiceDep, CurrentUser, DbSession, GithubServiceDep
from app.github.repository import SqlAlchemyGithubConnectionRepository
from app.github.schemas import GithubConnectionCreate, GithubConnectionResponse, GithubProjectImport
from app.github.webhooks import verify_github_signature
from app.projects.repository import SqlAlchemyProjectRepository

router = APIRouter(prefix="/github", tags=["github"])


@router.post("/connections", response_model=GithubConnectionResponse, status_code=201)
async def create_connection(body: GithubConnectionCreate, user: CurrentUser, svc: GithubServiceDep):

    return await svc.create_connection(user.user_id, body)


@router.get("/connections", response_model=list[GithubConnectionResponse])
async def list_connections(user: CurrentUser, svc: GithubServiceDep):

    return await svc.list_connections(user.user_id)


@router.delete("/connections/{conn_id}", status_code=204)
async def delete_connection(conn_id: str, user: CurrentUser, svc: GithubServiceDep):

    return await svc.delete_connection(user.user_id, conn_id)


@router.get("/connections/{conn_id}/repos")
async def list_connection_repos(
    conn_id: str,
    user: CurrentUser,
    svc: GithubServiceDep,
    search: str | None = Query(default=None, min_length=1),
):

    return await svc.list_repositories(user.user_id, conn_id, search=search)


@router.post("/projects/import")
async def import_project(body: GithubProjectImport, user: CurrentUser, svc: GithubServiceDep):

    return await svc.import_repository(body, user.user_id)


@router.post("/webhooks")
async def receive_webhook(
    request: Request,
    db: DbSession,
    build_svc: BuildServiceDep,
    x_hub_signature: str | None = Header(default=None, alias="X-Hub-Signature-256"),
):
    """Public webhook receiver for GitHub App events.

    Verifies HMAC signature and handles `push` events by creating a Build.
    """
    body = await request.body()
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid json payload") from exc

    installation_id = payload.get("installation", {}).get("id")
    if installation_id is None:
        # Not an installation-scoped webhook; ignore
        return {"ok": True}

    gh_repo = SqlAlchemyGithubConnectionRepository(db)
    conn = await gh_repo.get_by_installation_id(str(installation_id))
    settings = get_settings()
    secret = None
    if conn and getattr(conn, "meta", None) and isinstance(conn.meta, dict):
        secret = conn.meta.get("webhook_secret")
    if not secret:
        secret = settings.github_webhook_secret

    if not verify_github_signature(secret or "", body, x_hub_signature):
        raise HTTPException(status_code=401, detail="invalid signature")

    event = request.headers.get("X-GitHub-Event")
    if event == "push":
        repo_full = payload.get("repository", {}).get("full_name")
        if conn and repo_full:
            proj_repo = SqlAlchemyProjectRepository(db)
            project = await proj_repo.find_by_github_repo(conn.id, repo_full)
            if project:
                build_data = BuildCreate(
                    project_id=project.id,
                    source_ref=payload.get("ref"),
                    commit_sha=payload.get("after"),
                    source_snapshot=payload,
                )
                await build_svc.create_build(build_data)

    return {"ok": True}
