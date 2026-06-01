# Runtime Wiring

This directory contains example runtime wiring for the builder processes that live outside the HTTP control plane.

The long-term Cloudflare queue consumer is now being moved into the standalone
Go service in `../builder_worker/`. The Python worker wiring here remains a
temporary reference path until that port is complete.

For the canonical Go worker deployment examples, see:

- `../builder_worker/.env.example`
- `../builder_worker/deploy/README.md`
- `../builder_worker/deploy/systemd/cloudflare-builder-worker.service`
- `../builder_worker/deploy/systemd/cloudflare-builder-worker.env.example`

## Current builder entrypoints

- `uv run fake-builder-worker`
  - temporary local Celery-backed builder
- `uv run cloudflare-builder-worker`
  - Cloudflare HTTP pull-consumer builder

## Suggested deployment shape

- run the FastAPI control plane separately
- run one or more `cloudflare-builder-worker` processes on self-hosted builder nodes
- use an env file with `CP_` settings
- switch `CP_BACKGROUND_BUILDER_PROVIDER=cloudflare` when you want the control plane to enqueue to Cloudflare Queues instead of the local Celery path

## Files

- `systemd/cloudflare-builder-worker.service`
  - example long-running Cloudflare pull-consumer unit
- `systemd/cloudflare-builder-worker.env.example`
  - example env file for the Cloudflare pull-consumer unit
- `systemd/fake-builder-worker.service`
  - example long-running local Celery worker unit
- `systemd/fake-builder-worker.env.example`
  - example env file for the temporary local Celery worker
