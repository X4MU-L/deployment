# Control Plane

This service now supports a complete v1 static flow for manual public GitHub repo intake:

1. Register or log in.
2. Create a project with a public `https://github.com/{owner}/{repo}` URL.
3. Trigger a build from `/api/v1/projects/{project_id}/builds`.
4. Let the fake builder worker pick up the queued build.
5. Read build logs, build status, release details, and active route through user-scoped APIs.

## Temporary CeleryBuilder Adapter

The current local background build plane is a temporary **CeleryBuilder** adapter.
It is useful for local development and automated tests, but it is **not** the final
Cloudflare Queues worker described in the product docs.

```bash
cd control_plane
uv run fake-builder-worker
```

When a user triggers `POST /api/v1/projects/{project_id}/builds`, the control plane:

- creates the build in `queued` state
- resolves a `BackgroundBuilder` implementation from config
- uses the local `CeleryBuilder` adapter when `background_builder_provider=fake-builder`
- dispatches `celery_builder.process_build` to Celery
- stores the returned `queue_job_id` on the build record as an adapter-specific job reference

The `CFBuilder` adapter is intentionally separate from Celery and now drives the
Cloudflare-queue path for builds that are dispatched through Cloudflare. Celery
remains the temporary local-development adapter; Cloudflare remains the target
production build-plane adapter.

The Cloudflare-facing path is now partially defined:

- builds preallocate a `planned_release_id`
- `CFBuilder` constructs a real `build.requested.v1` payload
- `CFBuilder` can publish that payload to Cloudflare Queues through the Cloudflare API
- the intended long-running Cloudflare consumer now starts in `../builder_worker/` as a standalone Go service
- `cloudflare-builder-worker` inside `control_plane/` remains a temporary Python reference path while the Go worker is being ported
- the pull worker now forwards both the queue message's checkout/build spec and its artifact target into the executor path, so the external build request contract drives execution rather than being recomputed locally
- the pull worker forwards the full `artifact_target` from the queue message, so the queue contract is the source of truth for artifact bucket/prefix/manifest placement
- the Go worker now has a real R2 publisher path using the AWS SDK against Cloudflare R2's S3-compatible API
- the payload already includes a release-scoped R2 artifact target such as
  `projects/<project_id>/releases/<release_id>/...`

The remaining missing pieces are live Cloudflare credentials, a real queue ID/account ID, and production deployment wiring for the external consumer process.

## Temporary Artifact Store Adapter

The current artifact store is also adapter-backed:

- `artifact_store_provider=local` resolves `LocalArtifactStore`
- `artifact_store_provider=r2` resolves `R2ArtifactStore`

For now, `LocalArtifactStore` is the working local-development adapter that writes release files under the local artifact root while preserving the same `r2://bucket/key` contract shape used by the rest of the platform.

`R2ArtifactStore` now uses Cloudflare R2's S3-compatible API shape. It is ready for real use once `r2_endpoint_url`, `r2_access_key_id`, and `r2_secret_access_key` are configured. The control plane and routing contract now depend on the shared artifact-store interface instead of directly depending on filesystem code.

The worker then:

- fetches the build through the service-authenticated internal API
- simulates a public GitHub checkout/build
- writes ordered logs back to the control plane
- publishes simulated static files plus `static_release_manifest.v1` through the configured artifact-store adapter
- activates the static release route

If you want to run the fake build logic directly against a single build id during development, the helper command still exists:

```bash
cd control_plane
uv run fake-builder --base-url http://127.0.0.1:8000 --build-id <build-id>
```

## Temporary Python Cloudflare Pull Worker

The external Cloudflare consumer process can be started with:

```bash
cd control_plane
uv run cloudflare-builder-worker --once
```

The long-term replacement is the Go service in `../builder_worker/`.

## Migrations (Alembic)

- Alembic reads `CP_DATABASE_URL` from `.env` (defaults to `sqlite+aiosqlite:///./control_plane.db`).
- Create a new migration after changing models:

```bash
cd control_plane
alembic revision --autogenerate -m "describe change"
```

- Apply migrations:

```bash
cd control_plane
alembic upgrade head
```

For long-running deployment examples, see:

- `deploy/systemd/cloudflare-builder-worker.service`
- `deploy/systemd/cloudflare-builder-worker.env.example`
- `deploy/systemd/fake-builder-worker.service`
- `deploy/systemd/fake-builder-worker.env.example`
- `.env.example`

## Supported V1 Source Shape

- public GitHub repositories only
- HTTPS repo URLs only
- static runtime only

Unsupported sources fail cleanly in the fake builder flow so the user can still inspect the failed build and its logs.
