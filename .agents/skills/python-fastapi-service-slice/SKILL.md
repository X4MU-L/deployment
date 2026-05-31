---
name: python-fastapi-service-slice
description: Use when adding or changing a complete service-oriented feature in a Python FastAPI application: domain service, endpoint, schemas, repository/port, SQLAlchemy model, dependency injection, migrations, errors, and tests. Portable across FastAPI projects that favor clean layering and composition.
---

# Python FastAPI Service Slice

## Purpose

Create a complete FastAPI feature around a service layer, using a clean architecture style:

```text
endpoint -> service -> repository/interface -> database/external adapter
```

Use this skill for requests like:

- "Create a billing service"
- "Add an endpoint to reserve a resource"
- "Persist request logs"
- "Add a domain workflow with FastAPI, SQLAlchemy, and DI"

## First Questions

Before editing, infer or answer:

- What domain object does this service act on?
- Is it a new aggregate, or behavior on an existing object?
- Is the feature user-facing, internal, worker-only, or system-to-system?
- Does it persist state? If yes, create or update a model and migration.
- Does it read or write external state? If yes, introduce a repository/adapter port.
- What business rules belong in the service instead of the endpoint?
- What collaborators does the service compose: repositories, cache, token helpers, settings, HTTP clients, queues, clocks?
- What auth/permission guard applies?
- What stable error codes or exception types should callers rely on?

## Discover The Local Structure

Map the project before choosing paths:

- Find the app package: commonly `app/`, `src/<name>/`, or `<project>/`.
- Find existing routers/endpoints: `api/`, `routes/`, `endpoints/`.
- Find schemas: `schemas.py`, `dto.py`, `models.py`, or feature-local `schemas.py`.
- Find services: `service.py`, `services/`, or feature modules.
- Find persistence: `db/models/`, `models/`, `repositories/`, `storage/`.
- Find DI: `dependencies.py`, `container.py`, `providers.py`, or app factory wiring.
- Find tests and factories.

Prefer the project’s existing names and layout. If no pattern exists, use:

```text
app/
  api/v1/endpoints/<feature>.py
  <feature>/schemas.py
  <feature>/service.py
  <feature>/repository.py
  db/models/<thing>.py
  core/dependencies.py
tests/
  test_<feature>.py
  unit/test_<feature>_service.py
```

## Layer Responsibilities

- Endpoint: HTTP concerns only: request body, auth dependency, call service, return response schema.
- Schema: request/response validation and serialization only.
- Service: business rules, ownership checks, orchestration, mapping domain results to response objects.
- Repository port: operations the service needs, described as an interface/protocol/ABC.
- Repository adapter: SQLAlchemy or external implementation.
- Model: persisted shape and relational constraints.
- DI: compose repositories, services, clients, caches, settings.

Do not put SQLAlchemy queries in endpoints. Do not return ORM objects from endpoints.

## Service Design

Create a service when behavior has business rules, multiple steps, permissions, or persistence.

A service should:

- Be stateless per request.
- Receive collaborators through `__init__`.
- Depend on interfaces/ports when possible.
- Validate domain invariants before mutation.
- Raise project exception types or introduce consistent typed exceptions.
- Keep computed response mapping in helpers when endpoints would otherwise become noisy.

Skeleton:

```python
from __future__ import annotations


class ThingService:
    def __init__(self, repository: ThingRepository, clock: Clock | None = None) -> None:
        self._repository = repository
        self._clock = clock

    def create(self, payload: CreateThingRequest, actor_id: str) -> ThingResponse:
        self._validate(payload)
        record = self._repository.create(...)
        return _to_response(record)
```

## Repository Decision

Create a repository when the service needs persisted state, complex queries, or a replaceable external data source.

Repository interface methods should match business needs, not raw CRUD by default:

- `create(...)`
- `get_by_id(...)`
- `get_by_owner(...)`
- `list_active_by_user(...)`
- `mark_deleted(...)`
- `record_event(...)`

Use a domain record/dataclass or typed DTO as the repository return value. Avoid leaking ORM models into services unless the local project already does.

## Model Decision

Create or update a model when the feature introduces durable state or new queryable fields.

Ask:

- What is the primary key?
- Which fields are unique?
- Which fields are indexed for lookups?
- Is deletion soft or hard?
- Does the model need `created_at`, `updated_at`, `status`, or ownership fields?
- Are relationships needed for joins or cascade behavior?

Use migrations whenever schema changes. Keep application code and migration in the same task.

## DI Wiring

Wire dependencies in the project’s central DI place.

Typical flow:

```python
def get_thing_repository(session: DbSession) -> ThingRepository:
    return SQLThingRepository(session)


def get_thing_service(
    repo: Annotated[ThingRepository, Depends(get_thing_repository)],
) -> ThingService:
    return ThingService(repository=repo)


ThingServiceDep = Annotated[ThingService, Depends(get_thing_service)]
```

Endpoints should import the dependency alias, not build services directly.

## Endpoint Pattern

```python
router = APIRouter(prefix="/things", tags=["things"])


@router.post("", response_model=ThingResponse, status_code=201)
def create_thing(
    payload: CreateThingRequest,
    principal: CurrentPrincipalDep,
    service: ThingServiceDep,
) -> ThingResponse:
    return service.create(payload, actor_id=principal.user_id)
```

Register the router wherever the project collects API routes.

## Tests

Add tests at the right layer:

- Service unit tests with fake repositories for business rules and error cases.
- Endpoint tests for auth, validation, status codes, and response shape.
- Repository/integration tests for SQL queries, constraints, and migrations.

Always include:

- Happy path.
- Permission/auth failure if relevant.
- Validation/business-rule failure.
- Conflict/duplicate path if uniqueness exists.
- Persistence behavior if state changes.

Run the project’s formatter/linter/test command. Common commands:

```bash
pytest
ruff check .
ruff format --check .
```
