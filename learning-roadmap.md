# Learning Roadmap (What To Learn + In What Order)

This roadmap follows the approved product sequence rather than the broadest possible system shape.

## Phase 0: Mental Models

Learn first:

- control plane truth vs edge cache
- static-first product scoping
- intent vs reality
- sync APIs vs async jobs vs SSE streams

## Phase 1: Control Plane Core

Learn:

- Postgres-backed state models
- idempotent trigger semantics
- SSE with `Last-Event-ID`
- route-resolution contract design

Exercise:

- design build and release lifecycle around one static deployment

## Phase 2: Queue-Driven Build Flow

Learn:

- Cloudflare Queues pull consumers
- at-least-once delivery
- claim/lease thinking for duplicate prevention
- message size discipline

Exercise:

- implement `build.requested.v1` and a safe build-consumer loop

## Phase 3: Docker-Isolated Static Builds

Learn:

- ephemeral build workspaces
- log capture and sequencing
- immutable artifact packaging
- manifest generation

Exercise:

- turn a repo plus build commands into an R2-ready static release

## Phase 4: Worker Routing + R2

Learn:

- Worker route resolution and short-TTL caching
- immutable asset cache headers
- HTML vs asset caching policy
- streaming response handling in Workers

Exercise:

- serve one active static release on a wildcard hostname

## Phase 5: Dashboard On Workers

Learn:

- Next.js on Workers via OpenNext
- cookie-session auth
- SSR + streaming
- same-origin SSE proxy pattern

Exercise:

- build a page that triggers a deploy and tails logs live

## Phase 6: Hardening + Observability

Learn:

- correlation IDs across requests, jobs, and logs
- R2-backed log replay
- cost hotspots for Workers, Queues, and R2
- route rollback and cache propagation

## Later: Container Alpha

Only after the static product is stable, learn:

- runner agents
- health-checked container rollout
- origin routing for container traffic

## Suggested Build Order

1. Control plane state and APIs
2. queue-driven static build pipeline
3. R2 artifacts and manifest
4. Worker route resolution and static serving
5. dashboard experience
6. hardening
7. container alpha
