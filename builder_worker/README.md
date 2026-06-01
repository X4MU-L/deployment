# Builder Worker

This service is the intended home of the external build-plane consumer.

It is a standalone Go worker that:

- pulls `build.requested.v1` from Cloudflare Queues over HTTP
- classifies malformed versus retryable failures
- acks or retries queue messages explicitly
- exposes a handler boundary for build execution against the control plane

## Status

This is the canonical scaffold for the Go build worker described in
[services/build-plane.md](../services/build-plane.md).

The existing Python pull consumer inside `control_plane/` should now be treated
as a temporary reference path, not the intended final architecture.

The current Go port now supports two execution modes behind the same handler:

- `simulated`
  - emits placeholder build phases and publishes a synthetic static release
- `actual`
  - clones the requested repo into an ephemeral workspace
  - checks out the requested ref or commit
  - runs install/build commands with live log streaming over the executor channel
  - validates the declared output directory
  - publishes the real built output through the artifact publisher

Current limitation:

- artifact publishing now sits behind a `Publisher` interface
- the local publisher is working today
- the R2 publisher is now implemented using the Go AWS SDK against Cloudflare R2's S3-compatible API
- the current simulated build handler can publish through either the local or R2 publisher path, depending on config
- the worker now separates orchestration from execution and log transport:
  - handler owns control-plane callbacks
  - executor owns build behavior and artifact production
  - log forwarding is a separate adapter that consumes executor log channels and writes them to the control plane
- executor selection is factory-driven:
  - `simulated` is useful for local contract checks
  - `actual` is the current real checkout/build path
- current limitation:
  - the `actual` executor now defaults to Docker for command execution
  - the next hardening step is tightening container policy further, especially per-project image policy and stronger runtime limits

## Layout

- `cmd/cloudflare-builder-worker/`
  - process entrypoint and lifecycle wiring
- `internal/config/`
  - environment-driven configuration
- `internal/contracts/`
  - `build.requested.v1` contract types and validation
- `internal/queue/`
  - Cloudflare Queues HTTP pull/ack client
- `internal/consumer/`
  - poll loop and retry classification
- `internal/artifacts/`
  - artifact publisher interface plus local and R2 adapters
- `internal/handler/`
  - control-plane orchestration around a build execution
- `internal/executor/`
  - simulated executor plus the current real checkout/build executor

## Environment

- `CP_CLOUDFLARE_API_BASE_URL`
- `CP_CLOUDFLARE_ACCOUNT_ID`
- `CP_CLOUDFLARE_API_TOKEN`
- `CP_CLOUDFLARE_QUEUE_ID`
- `CP_CLOUDFLARE_PULL_BATCH_SIZE`
- `CP_CLOUDFLARE_PULL_VISIBILITY_TIMEOUT_MS`
- `CP_CLOUDFLARE_PULL_POLL_INTERVAL_SECONDS`
- `CP_CLOUDFLARE_PULL_MAX_ATTEMPTS`
- `CP_CELERY_BUILDER_BASE_URL`
- `CP_INTERNAL_SERVICE_TOKEN`
- `CP_CELERY_BUILDER_SERVICE_NAME`
- `CP_BUILD_EXECUTOR_PROVIDER`
- `CP_BUILD_COMMAND_RUNNER_PROVIDER`
- `CP_BUILD_DOCKER_IMAGE`
- `CP_BUILD_DOCKER_ALLOWED_IMAGES`
- `CP_BUILD_DOCKER_INSTALL_NETWORK`
- `CP_BUILD_DOCKER_BUILD_NETWORK`
- `CP_BUILD_DOCKER_PIDS_LIMIT`
- `CP_ARTIFACT_STORE_PROVIDER`
- `CP_ARTIFACT_STORE_ROOT`
- `CP_R2_ENDPOINT_URL`
- `CP_R2_ACCESS_KEY_ID`
- `CP_R2_SECRET_ACCESS_KEY`
- `CP_R2_SESSION_TOKEN`
- `CP_R2_REGION_NAME`

The `actual` executor now defaults to a Docker-backed command runner in the
factory path. The next step is to harden that container runtime further with
tighter image policy, network controls, and workspace hygiene while keeping the
queue client, handler, and log-forwarding contracts stable.
