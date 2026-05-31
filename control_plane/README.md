# Control Plane

This service now supports a complete v1 static flow for manual public GitHub repo intake:

1. Register or log in.
2. Create a project with a public `https://github.com/{owner}/{repo}` URL.
3. Trigger a build from `/api/v1/projects/{project_id}/builds`.
4. Let the fake builder worker pick up the queued build.
5. Read build logs, build status, release details, and active route through user-scoped APIs.

## Fake Builder Worker

Use the Celery-backed fake builder while the real queue consumer and Docker executor are still being developed.

```bash
cd control_plane
uv run fake-builder-worker
```

When a user triggers `POST /api/v1/projects/{project_id}/builds`, the control plane:

- creates the build in `queued` state
- dispatches `fake_builder.process_build` to Celery
- stores the returned `queue_job_id` on the build record

The worker then:

- fetches the build through the service-authenticated internal API
- simulates a public GitHub checkout/build
- writes ordered logs back to the control plane
- marks the build succeeded with fake R2 artifact and manifest refs
- activates the static release route

If you want to run the fake build logic directly against a single build id during development, the helper command still exists:

```bash
cd control_plane
uv run fake-builder --base-url http://127.0.0.1:8000 --build-id <build-id>
```

## Supported V1 Source Shape

- public GitHub repositories only
- HTTPS repo URLs only
- static runtime only

Unsupported sources fail cleanly in the fake builder flow so the user can still inspect the failed build and its logs.
