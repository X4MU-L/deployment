# Engineering Standards (Languages, Services, and Patterns)

This document is the canonical reference for:

- the approved language split
- plane and service ownership
- the clean-architecture bias across services
- coding rules that help the system scale without unnecessary complexity

## Scope: This Workspace Is The Project

This workspace owns the platform design and implementation.

- Root docs and `services/` docs are the canonical product specification.
- `control_plane/` is an implementation in progress.
- Reference repos in this workspace remain read-only examples.

## Product Direction

The project is explicitly:

- **Cloudflare-first at the edge**
- **static-first for the first sellable product**
- **self-hosted for canonical state and untrusted compute**

Container runtime support is a later milestone, not equal day-one scope.

## Polyglot Stack (current)

- **Control plane**: Python 3.12 + FastAPI + SQLAlchemy + Pydantic
  - canonical state and orchestration
- **Builders, runners, and long-running agents**: Go
  - concurrency, external queue consumers, runtime agents
- **Dashboard and edge routing**: TypeScript
  - Next.js on Cloudflare Workers via OpenNext for the dashboard
  - plain Worker logic for wildcard static routing
- **Infrastructure**: Ansible
  - deployment roles, templates, and service wiring

## Service Inventory

### Edge Plane (Cloudflare)

- **Dashboard Worker**
  - SSR/streaming UI
  - cookie-authenticated operator experience
  - same-origin SSE proxy for logs
- **Routing Worker**
  - resolves `*.apps.<domain>` hostnames
  - serves static releases from R2
  - later forwards container traffic to a stable origin router

### Control Plane (Self-hosted)

Owns:

- users, orgs, projects
- build and release state
- route intent
- build job production
- build log ingestion and SSE streaming
- internal route resolution for the Worker

### Build Plane (Self-hosted)

Owns:

- external queue consumption
- source checkout
- Docker-isolated static builds
- R2 artifact and manifest upload
- status and log callbacks to control plane

### Runtime Plane (Later)

Owns:

- container lifecycle
- health checks
- runtime logs
- rollout coordination for container apps

Not part of the first sellable product.

### Routing Plane (Hybrid)

- **Initial product**: Worker-first static routing
- **Later container alpha**: Worker front door plus origin router to runners

## Architectural Pattern

### Between Services

- The control plane is the orchestrator and source of truth.
- Edge services never invent route truth; they cache and consume it.
- Builders and runners are stateless agents around explicit work contracts.
- Communication styles:
  - HTTPS JSON for APIs and callbacks
  - SSE for one-way log streaming
  - Cloudflare Queues for build jobs only in the first product

### Inside A Service

Default to Hexagonal / Clean Architecture:

- inbound adapters: HTTP handlers, queue consumers, Worker routes
- domain: orchestration and rules
- outbound adapters: Postgres, R2, Queues, registry, Docker
- ports: small interfaces owned by the consumer side

## Coding Style Rules

### Functional Core + Imperative Shell

- keep I/O at the edge
- keep transformations and decisions testable in pure-ish functions

### Composition Over Inheritance

- inject collaborators
- keep interfaces narrow
- avoid framework-heavy service objects that own too much behavior

### Contract-First Thinking

- version queue messages
- keep internal sync contracts explicit
- write down resumability and idempotency behavior
- do not rely on implied payload shapes across processes

## v1 Constraints

- Postgres is canonical from the start
- Redis is optional and later
- queue payloads must stay comfortably below `64 KB`
- no long-lived shared secrets embedded in build jobs
- static release paths should be immutable and cache-friendly

## Definition Of Done

A change is done when:

- the owning plane and contract are explicit
- docs remain in sync with implementation
- queue consumers and callbacks are idempotent where required
- secrets are never logged or returned
- tests cover both core logic and the touched contract surface

## Language-Specific Conventions

### Python

- thin FastAPI endpoints
- service layer owns orchestration
- repositories own persistence boundaries
- central DI wiring

### Go

- `cmd/` is wiring only
- `internal/` packages own real logic
- every goroutine has an owner and shutdown path
- long-running consumers must make retries and visibility behavior explicit

### TypeScript

- server-side auth decisions first
- same-origin SSE proxying for operator UI
- TanStack Query for server state
- avoid storing per-request data in module scope
- Worker code must stream, not buffer, large responses
