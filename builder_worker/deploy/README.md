# Builder Worker Deployment

This directory contains example runtime wiring for the standalone Go build
worker service in `builder_worker/`.

## Current shape

- the worker is intended to run outside the control plane
- it pulls `build.requested.v1` from Cloudflare Queues over HTTP
- it talks back to the control plane through the internal build APIs

## Current limitation

The Go worker currently ports the simulated local-development build lifecycle:

- queue consumption
- control-plane status/log/complete callbacks
- local artifact-store publishing under `CP_ARTIFACT_STORE_ROOT`

Real R2 publishing is the next step.

## Example files

- `systemd/cloudflare-builder-worker.service`
- `systemd/cloudflare-builder-worker.env.example`

Use `.env.example` in the service root for local development defaults.
