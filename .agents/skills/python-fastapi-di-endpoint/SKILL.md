---
name: python-fastapi-di-endpoint
description: Use when adding FastAPI endpoints and dependency wiring around existing services: routers, dependency aliases, auth guards, response models, route registration, and endpoint-level tests.
---

# Python FastAPI DI Endpoint

## Purpose

Expose service behavior over HTTP while keeping endpoint functions thin and dependency wiring centralized.

Use this when:

- A service already exists and needs an API route.
- A new endpoint needs auth, a repository-backed service, settings, cache, or external adapter.
- Endpoints are manually constructing collaborators and need cleanup.

## First Questions

- Which service method is exposed?
- What request schema and response schema already exist or must be created?
- What auth guard applies?
- Is the endpoint public, user-authenticated, admin-only, or internal service-to-service?
- What status code is correct?
- Should the endpoint return a resource, list, empty `204`, or an operation result?

## Dependency Wiring

Find the central DI file. Common names:

- `app/core/dependencies.py`
- `app/dependencies.py`
- `dependencies.py`
- `container.py`
- app factory provider functions

Add dependencies in layers:

```python
DbSession = Annotated[Session, Depends(get_db)]


def get_repository(session: DbSession) -> Repository:
    return SQLRepository(session)


def get_service(
    repo: Annotated[Repository, Depends(get_repository)],
) -> Service:
    return Service(repository=repo)


ServiceDep = Annotated[Service, Depends(get_service)]
```

Prefer endpoint signatures that use aliases:

```python
def create_item(payload: CreateItemRequest, service: ServiceDep) -> ItemResponse:
    ...
```

## Endpoint Rules

- Endpoints validate transport input, call a service, and return schemas.
- Do not place SQL queries, external HTTP calls, or multi-step business workflows in endpoint functions.
- Do not return ORM models unless the project explicitly standardizes on that.
- Use `response_model` for public API shape.
- Use status codes intentionally: `201` create, `200` read/update, `204` empty delete/action.
- Keep route tags and prefixes consistent with nearby routers.

## Router Registration

Create or update the endpoint module:

```python
router = APIRouter(prefix="/items", tags=["items"])
```

Register it in the project’s API router:

```python
api_router.include_router(items_router)
```

If the project uses app factory registration, add it there instead.

## Auth Dependencies

Use existing auth dependency aliases when present:

- Current user/principal.
- API key/shared secret.
- Admin guard.
- Optional principal.

If adding a new guard:

- Put parsing/validation in DI, not the endpoint.
- Return a typed principal/context object.
- Raise the project’s standard auth exception.
- Keep dev-mode bypasses explicit and consistent with existing settings.

## Tests

Endpoint tests should verify:

- Route is registered.
- Request validation errors.
- Auth missing/invalid.
- Happy response status and body.
- Service error translation to expected HTTP shape.

Use dependency overrides where the project supports them. Otherwise use test fixtures/factories already present.
