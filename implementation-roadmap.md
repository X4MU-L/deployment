# Implementation Roadmap — Cloudflare-First, Static-First

This file is the canonical delivery roadmap for the approved product direction.

## Guiding Principles

- Ship a complete static deploy product before broadening scope.
- Keep `deployment/` docs and contracts authoritative.
- Use Cloudflare where it reduces operational drag at the edge.
- Keep Docker builds, runtime scheduling, and other untrusted compute on self-hosted infrastructure.
- Assume at-least-once delivery for async workflows and design handlers to be idempotent.

## Initial Product Definition

The first milestone is done when a user can:

- create a project
- trigger a static build
- watch live build logs
- publish an immutable release to R2
- load the app on `*.apps.<domain>` without operator intervention

This milestone does **not** require:

- container runtime
- preview environments
- custom domains
- Redis
- multi-node scheduling

## Delivery Phases

### Phase 0 — Spec Hardening

Deliverables:

- root docs and `services/` docs explicitly say **Cloudflare-first, static-first**
- route resolution and static manifest contracts are frozen
- build-job scope is narrowed to `build.requested.v1`

Exit criteria:

- architecture, roadmap, and contracts are consistent
- container features are clearly marked as later work

### Phase 1 — Control Plane Core

Deliverables:

- Postgres-backed models for projects, builds, releases, and routes
- `POST /v1/projects`
- idempotent static build trigger
- build status updates and log ingest endpoints
- SSE log stream with `Last-Event-ID`
- `GET /internal/routes/resolve`

Exit criteria:

- the control plane is authoritative for build and route state
- a fake or real builder can drive a build lifecycle end to end

### Phase 2 — Dashboard On Workers

Deliverables:

- Next.js on Workers via OpenNext
- cookie-session auth flow
- same-origin SSE proxy endpoint
- static-first views for projects, builds, releases, and logs

Exit criteria:

- authenticated users can operate the static deploy flow from the dashboard
- log viewing works without cross-origin hacks

### Phase 3 — Build Pipeline

Deliverables:

- `build.requested.v1` queue producer
- external build worker using Cloudflare Queues HTTP pull
- static build in Docker
- R2 artifact upload
- `static_release_manifest.v1`
- release activation in control plane

Exit criteria:

- a real static build can move from queue to active release
- queue retries do not create duplicate active releases

### Phase 4 — Static Routing

Deliverables:

- Worker bound to `*.apps.<domain>`
- route resolution on cache miss
- short-lived route cache in the Worker
- immutable asset serving from R2
- fast rollback by keeping HTML/route metadata short-TTL

Exit criteria:

- active releases are reachable through wildcard routes
- route changes propagate within defined TTL expectations

### Phase 5 — Hardening

Deliverables:

- duplicate build protection via claim/lease flow
- durable log replay from R2
- rate limiting and auth hardening
- audit trail
- basic cost visibility for queue, Worker, and R2 usage

Exit criteria:

- duplicate delivery and reconnect flows are safe
- operators can reason about basic usage and cost

### Phase 6 — Container Alpha

Deliverables:

- `deploy.requested.v1`
- runner agent
- image pull and health checks
- stable origin router for container traffic
- Worker kept as front door only

Exit criteria:

- a container app can be deployed behind the existing front door
- container traffic does not require the Worker to know node topology

## Implementation Priorities Inside The First Product

Build this order inside the first product milestone:

1. Postgres-backed control-plane state and core APIs
2. SSE log ingest and resumable stream behavior
3. queue producer and external builder pull consumer
4. R2 upload plus manifest generation
5. Worker route resolution and static asset serving
6. dashboard experience on top of working APIs

This ordering keeps infrastructure truth ahead of UI polish.

## Key Contracts That Must Stay Stable

- `build.requested.v1`
- builder status and log ingest APIs
- `GET /internal/routes/resolve`
- `static_release_manifest.v1`

Breaking any of these requires coordinated doc and test updates.

## Testing Requirements By Phase

- Every phase needs unit coverage for core logic.
- Every phase needs at least one integration path test.
- The first product must include end-to-end validation of:
  - trigger build
  - consume queue
  - build static output
  - upload to R2
  - activate route
  - serve wildcard app

## Risks To Manage Early

- queue retries creating duplicate release activation
- log replay gaps on SSE reconnect
- large route or manifest payloads creeping toward queue limits
- uncached R2 read volume becoming expensive
- Worker route logic drifting from control-plane truth
