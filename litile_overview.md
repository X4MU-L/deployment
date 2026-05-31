# Deployment Platform: Hybrid Architecture Notes

This folder is the canonical design source for the deployment platform.

The product direction is now explicitly:

- **Cloudflare-first** at the edge
- **static-first** for the first sellable product
- **self-hosted** for canonical state and untrusted compute

## Decisions (current)

- First product: **static site deployments only**
- Container apps remain a **next milestone**, not equal day-one scope
- Cloudflare usage in the first product:
  - Workers for dashboard, SSE proxy, and static wildcard routing
  - R2 for immutable release artifacts and cold log archive
  - Queues for build jobs only
- Control plane state is **Postgres-first**
- Redis is **not** required in the initial product
- Real-time logs use **SSE**
- Service style stays **decoupled with explicit contracts**

## Read This In Order

1. [architecture.md](architecture.md) — big picture, product scope, and phase boundaries
2. [engineering-standards.md](engineering-standards.md) — language choices, plane ownership, and implementation rules
3. [implementation-roadmap.md](implementation-roadmap.md) — phased delivery plan for the approved direction
4. [services/control-plane.md](services/control-plane.md) — state ownership, sync APIs, SSE, and route resolution
5. [services/build-plane.md](services/build-plane.md) — build jobs, Docker isolation, R2 upload, manifest output
6. [services/routing-plane.md](services/routing-plane.md) — Worker-first static routing and later container routing
7. [platform-contracts.md](platform-contracts.md) — frozen internal route-resolution and static release manifest contracts
8. [client-dashboard.md](client-dashboard.md) — dashboard architecture and same-origin SSE proxy pattern
9. [event-schemas.md](event-schemas.md) — queue messages and versioning rules
10. [learning-roadmap.md](learning-roadmap.md) — build-order-aligned learning path

## Relationship To `control_plane/`

`control_plane/` is an ongoing implementation. It is useful context, but the canonical decisions and contracts live in these root docs and the `services/` docs.

When implementation and design diverge:

- update the docs if the product decision changed intentionally
- update implementation if the docs remain the intended source of truth

## Reference Implementations In This Workspace

These remain read-only references:

- `ngrok_alternative/control_plane/` — FastAPI DI, auth, and repository patterns
- `ngrok_alternative/data_plane/` — Go concurrency and network-agent patterns
- `fasttunnel-cli-extract/` — Go CLI parsing and telemetry conventions
- `ngrok_alternative/infra/` — Ansible role and template patterns

Prefer implementing authoritative platform behavior in this workspace, not in the reference repos.
