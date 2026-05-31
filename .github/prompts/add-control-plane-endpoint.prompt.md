---
description: "Add a new FastAPI control-plane endpoint with Pydantic schemas, DI wiring, service method, repository method, and pytest coverage."
name: "Add Control Plane Endpoint"
argument-hint: "Method + path, auth requirements, request/response shape, side effects"
agent: "Python Control Plane"
---
Implement a new control-plane endpoint following the existing patterns.

If implementing a new deployment-platform control plane service, mirror the patterns from `ngrok_alternative/control_plane/` (reference implementation). Prefer updating `deployment/` for authoritative contracts.

Constraints:
- Endpoints stay thin (validation + call service + return schema).
- Business logic goes in a stateless service.
- Persistence goes through a repository interface (port) + SQLAlchemy implementation.
- Wire DI centrally via the repo’s `app/core/dependencies.py` (reference: `ngrok_alternative/control_plane/app/core/dependencies.py`).
- Use project exception types with stable `code` values.

Deliverables:
- Endpoint + schemas
- Service method
- Repo interface + implementation changes
- Tests (pytest) covering success + error cases
- Commands to validate (`ruff`, `pytest`) if you don’t run them
