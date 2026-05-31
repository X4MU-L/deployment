from fastapi import APIRouter

from app.core.dependencies import ReleaseServiceDep
from app.releases.schemas import ReleaseCreate, ReleaseResponse, RouteCreate, RouteResponse

router = APIRouter(prefix="/releases", tags=["releases"])


@router.post("/", response_model=ReleaseResponse, status_code=201)
async def create_release(body: ReleaseCreate, svc: ReleaseServiceDep):
    return await svc.create_release(body)


@router.get("/environment/{environment_id}", response_model=list[ReleaseResponse])
async def list_releases(environment_id: str, svc: ReleaseServiceDep):
    return await svc.list_releases(environment_id)


@router.get("/{release_id}", response_model=ReleaseResponse)
async def get_release(release_id: str, svc: ReleaseServiceDep):
    return await svc.get_release(release_id)


# --- Routes ---
@router.post("/routes/", response_model=RouteResponse, status_code=201)
async def create_route(body: RouteCreate, svc: ReleaseServiceDep):
    return await svc.create_route(body)


@router.get("/{release_id}/routes", response_model=list[RouteResponse])
async def list_routes(release_id: str, svc: ReleaseServiceDep):
    return await svc.list_routes(release_id)


@router.delete("/routes/{route_id}", status_code=204)
async def delete_route(route_id: str, svc: ReleaseServiceDep):
    await svc.delete_route(route_id)
