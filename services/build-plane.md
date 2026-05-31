# Build Plane (Builder Service)

The build plane turns source code plus build settings into an immutable static release.

For the approved initial product, the build plane focuses on **static builds only**.

## Responsibilities

- consume `build.requested.v1` from Cloudflare Queues via HTTP pull
- clone source at a specific commit SHA
- run a static build in Docker-isolated environments
- stream build logs to the control plane
- upload release files and manifest to R2
- report terminal build status back to the control plane

## Builder Topology

- disposable stateless builder instances
- concurrency limited by host CPU/RAM and operator policy
- queue delivery is at-least-once, so callback behavior must be idempotent

## Input Contract

Input is `build.requested.v1`.

Required fields:

- `project_id`
- `build_id`
- `release_id`
- git checkout metadata
- `build_spec.kind=static`
- `artifact_target` with R2 location

Rules:

- keep the queue payload comfortably below `64 KB`
- do not embed long-lived secrets in the message

## Isolation Model

Minimum viable isolation:

- build inside an ephemeral Docker container
- use an ephemeral workspace per build
- discard the workspace after completion

Hardening later:

- dedicated builder nodes
- tighter outbound network controls
- stronger duplicate-claim protection

## Output Contract

### Static artifact

Upload release contents to R2 under a stable immutable prefix, for example:

- `projects/<project_id>/releases/<release_id>/...`

### Manifest

Upload `static_release_manifest.v1` alongside the release.

The manifest must include:

- release id
- build id
- index document
- asset paths
- content hashes
- cache policy

See [platform-contracts.md](../platform-contracts.md) for the frozen manifest shape.

### Completion callback

On success, the builder reports:

- build terminal state
- artifact location
- manifest location

## Build Logs

### Real-time

- send ordered chunks to the control plane as the build runs

### Replay

- archive the complete log to R2 after completion

The initial product should not use the queue for log transport.

## Auth

Builder-to-control-plane auth must be service scoped.

Preferred options:

- short-lived signed token
- scoped service token issued outside the queue payload

Avoid embedding a permanent shared secret inside the message body.

## Idempotency And Duplicate Delivery

Required:

- terminal status updates must be safe to retry
- release activation must remain under control-plane authority

Later hardening:

- add a build claim or lease endpoint to prevent duplicate heavy work across consumers

## Non-goals For This Milestone

- container image builds
- registry push flow
- deploy job production
- build cache optimization before correctness
