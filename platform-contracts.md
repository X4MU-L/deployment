# Platform Contracts (Frozen For The Initial Product)

This document records the contract surfaces that must stay stable across the control plane, builder, dashboard, and routing Worker during the initial product milestone.

## Internal Route Resolution

### Endpoint

`GET /internal/routes/resolve?hostname={hostname}`

Purpose:

- allow the routing Worker to resolve the active release for a wildcard hostname

Caller:

- routing Worker only

Authentication:

- service-to-service credential, not end-user auth

### Response Shape

```json
{
  "hostname": "myapp.apps.example.com",
  "route_kind": "static",
  "project_id": "proj_123",
  "release_id": "rel_789",
  "cache_ttl_seconds": 30,
  "invalidation_version": 4,
  "static_origin": {
    "r2_bucket": "artifacts",
    "r2_prefix": "projects/proj_123/releases/rel_789/",
    "manifest_path": "projects/proj_123/releases/rel_789/manifest.json",
    "index_document": "index.html"
  }
}
```

Rules:

- `route_kind` is `static` in the first product.
- `cache_ttl_seconds` should be short enough to support fast rollback.
- `invalidation_version` changes when the active route changes and lets edge caches detect stale resolution data.
- future container responses may add an `origin_target`, but static responses remain unchanged.

## Static Release Manifest

### Schema Name

`static_release_manifest.v1`

### Purpose

- describe the immutable release uploaded by the builder
- give the routing layer and operators a stable view of entrypoint and asset metadata

### Example

```json
{
  "schema": "static_release_manifest.v1",
  "project_id": "proj_123",
  "release_id": "rel_789",
  "build_id": "build_456",
  "generated_at": "2026-05-31T12:10:00Z",
  "index_document": "index.html",
  "error_document": null,
  "cache_policy": {
    "html_max_age_seconds": 30,
    "asset_max_age_seconds": 31536000,
    "asset_cache_control": "public, max-age=31536000, immutable"
  },
  "assets": [
    {
      "path": "index.html",
      "sha256": "4f9c4d7c...",
      "content_type": "text/html"
    },
    {
      "path": "assets/app-abc123.js",
      "sha256": "e2d4b871...",
      "content_type": "application/javascript"
    }
  ]
}
```

Rules:

- asset paths are immutable once published
- HTML and route metadata may have short TTLs
- hashed assets should be cacheable for long periods
- the manifest is uploaded alongside the release contents in R2

## Compatibility Rules

- additive fields are allowed when consumers tolerate unknown keys
- breaking changes require a new versioned schema or endpoint revision
- the dashboard, builder, control plane, and Worker must update together when these contracts change
