from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    builds,
    deployments,
    environments,
    github,
    health,
    internal,
    projects,
    releases,
)

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(health.router)
v1_router.include_router(auth.router)
v1_router.include_router(projects.router)
v1_router.include_router(environments.router)
v1_router.include_router(builds.router)
v1_router.include_router(deployments.router)
v1_router.include_router(releases.router)
v1_router.include_router(internal.router)
v1_router.include_router(github.router)
