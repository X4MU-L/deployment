# Event Schemas (Queues + Internal Events)

This document defines the async message contracts for the platform.

## Scope

For the first sellable product, the async queue scope is intentionally narrow:

- implement **build jobs**
- defer **deploy jobs** to the container milestone
- keep queue payloads small and versioned

## Principles

- **At-least-once delivery**: consumers must be idempotent.
- **Versioned types**: breaking changes require a new version suffix.
- **Explicit correlation**: every message carries identifiers for tracing.
- **Small payloads**: keep messages comfortably below `64 KB`; store large metadata in Postgres or R2.

Recommended shared fields:

- `type`
- `occurred_at`
- `message_id`
- `correlation_id`
- `project_id`
- `build_id` and/or `deployment_id`

## Build Job Message

### `build.requested.v1`

```json
{
  "type": "build.requested.v1",
  "occurred_at": "2026-05-31T12:00:00Z",
  "message_id": "b56c2a16-4bde-4bdf-88bf-4bdf0a7a9c6a",
  "correlation_id": "4c22f8a4-7a66-4ce6-b2a6-4eaa6a0f6a8b",
  "project_id": "proj_123",
  "build_id": "build_456",
  "release_id": "rel_789",
  "git": {
    "repo": "git@github.com:org/repo.git",
    "commit_sha": "abc123",
    "ref": "main"
  },
  "build_spec": {
    "kind": "static",
    "install": "pnpm i --frozen-lockfile",
    "build": "pnpm build",
    "output_dir": "dist"
  },
  "artifact_target": {
    "r2_bucket": "artifacts",
    "r2_prefix": "projects/proj_123/releases/rel_789/"
  }
}
```

Rules:

- `build_spec.kind` is `static` for the first product.
- secrets or large environment maps do not travel in the queue payload.
- worker-facing auth material should be fetched separately or provided through a scoped callback token.

## Deploy Job Message (Later)

### `deploy.requested.v1`

This message remains part of the future container milestone.

Do not make it part of the first static deploy acceptance criteria.

Example shape remains intentionally deferred until the runtime plane is actively being implemented.

## Status Events

Status transitions may be:

- written directly via control-plane APIs
- optionally published later for observability or fan-out

The first product should prefer direct API writes for simplicity.

Examples of later event names:

- `build.started.v1`
- `build.succeeded.v1`
- `build.failed.v1`
- `deployment.healthy.v1`

## Log Events

Do **not** push every log line through Cloudflare Queues.

Recommended flow:

- builder streams logs to the control plane over HTTP
- control plane exposes SSE for live tailing
- complete log archives are stored in R2

This keeps log latency low and queue cost predictable.

## Versioning Rules

- additive optional fields may remain in the same major version when consumers tolerate unknown fields
- breaking changes require a new versioned type such as `build.requested.v2`
- keep old consumers working until explicitly retired
