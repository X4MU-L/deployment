# Builder Worker

This service is the intended home of the external build-plane consumer.

It is a standalone Go worker that:

- pulls `build.requested.v1` from Cloudflare Queues over HTTP
- dispatches pulled jobs through a bounded-concurrency build hub
- classifies malformed versus retryable failures
- acks or retries queue messages explicitly
- exposes a handler boundary for build execution against the control plane
- renews active build claims during long-running builds so queue redelivery does not become duplicate execution
- emits structured lifecycle events on a dedicated `system` log stream with build and correlation context

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
  - can now isolate both source fetch and build execution through Docker-backed adapters

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
  - the `actual` executor now defaults to Docker for both source fetch and command execution
  - the next hardening step is tightening container policy further, especially per-project image policy and stronger duplicate-claim protection

## Layout

- `cmd/builder/`
  - process entrypoint and lifecycle wiring
- `internal/config/`
  - environment-driven configuration
- `internal/contracts/`
  - `build.requested.v1` contract types and validation
- `internal/queue/`
  - Cloudflare Queues HTTP pull/ack client
- `internal/consumer/`
  - poll loop, bounded job dispatch, and retry classification
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
- `CP_CLOUDFLARE_PULL_MAX_CONCURRENT_BUILDS`
- `CP_CELERY_BUILDER_BASE_URL`
- `CP_INTERNAL_SERVICE_TOKEN`
- `CP_CELERY_BUILDER_SERVICE_NAME`
- `CP_BUILD_CLAIM_LEASE_SECONDS`
- `CP_BUILD_CLAIM_RENEW_INTERVAL_SECONDS`
- `CP_BUILD_MAX_DURATION_SECONDS`
- `CP_BUILD_EXECUTOR_PROVIDER`
- `CP_SOURCE_FETCHER_PROVIDER`
- `CP_FETCH_DOCKER_IMAGE`
- `CP_FETCH_DOCKER_NETWORK`
- `CP_FETCH_DOCKER_CPUS`
- `CP_FETCH_DOCKER_MEMORY`
- `CP_FETCH_DOCKER_MEMORY_SWAP`
- `CP_FETCH_DOCKER_PIDS_LIMIT`
- `CP_BUILD_COMMAND_RUNNER_PROVIDER`
- `CP_BUILD_DOCKER_IMAGE`
- `CP_BUILD_DOCKER_ALLOWED_IMAGES`
- `CP_BUILD_DOCKER_INSTALL_NETWORK`
- `CP_BUILD_DOCKER_BUILD_NETWORK`
- `CP_BUILD_DOCKER_CPUS`
- `CP_BUILD_DOCKER_MEMORY`
- `CP_BUILD_DOCKER_MEMORY_SWAP`
- `CP_BUILD_DOCKER_PIDS_LIMIT`
- `CP_ARTIFACT_STORE_PROVIDER`
- `CP_ARTIFACT_STORE_ROOT`
- `CP_R2_ENDPOINT_URL`
- `CP_R2_ACCESS_KEY_ID`
- `CP_R2_SECRET_ACCESS_KEY`
- `CP_R2_SESSION_TOKEN`
- `CP_R2_REGION_NAME`

The `actual` executor now defaults to Docker-backed source fetch and command
execution in the factory path. The next step is to harden that runtime further
with tighter image policy, stronger duplicate-claim protection, and continued
workspace hygiene while keeping the queue client, handler, and log-forwarding
contracts stable.

The pull consumer now keeps a bounded in-flight job hub per worker process.
When there is spare capacity it can keep pulling additional queue work even
while earlier builds are still running, but queue messages are still only acked
or retried after the corresponding build result is known.

Active builds now also renew their control-plane claim on a fixed heartbeat
interval. That keeps long-running builds from losing ownership while they are
still executing, and lets the worker cancel a build if renewal fails or the
claim is no longer owned.

The worker now also emits structured lifecycle log entries for claim/start/
renew/finish phases on a dedicated `system` stream. Those events include the
build id, release id, attempt, service name, and correlation id so one build
can be traced across queue handoff, execution, and completion without relying
only on raw command output.

The Cloudflare queue visibility timeout should be at least as long as the
control-plane claim lease. The worker now defaults that timeout from
`CP_BUILD_CLAIM_LEASE_SECONDS` and rejects shorter values so long-running
builds are not redelivered after only a few seconds while the original worker
still legitimately owns the build.

The worker also enforces a maximum build duration that must stay below the
claim lease. That gives the current pull-queue model a hard upper bound for
one build’s execution time, so a stuck build is canceled before it can drift
past the queue/claim safety window.
