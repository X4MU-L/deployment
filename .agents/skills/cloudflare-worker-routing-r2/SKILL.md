---
name: cloudflare-worker-routing-r2
description: Use when creating or changing Cloudflare Worker routing for wildcard static apps, including Wrangler bindings, route resolution, short-TTL edge caching, R2 fetch behavior, immutable asset cache headers, and streamed responses.
---

# Cloudflare Worker Routing + R2

## Purpose

Implement the wildcard static app front door.

Use this when:

- building the `*.apps.<domain>` Worker
- wiring R2 bindings and route config
- resolving hostnames through the control plane
- setting cache behavior for HTML and immutable assets

## Default Flow

1. extract hostname and request path
2. resolve route from control plane on cache miss
3. load manifest or cached route metadata
4. map request path to the correct R2 object
5. return a streamed response with the right cache headers

## Rules

- Worker route truth is cached, not invented
- keep route resolution TTL short
- keep immutable asset TTL long
- do not buffer large R2 responses when forwarding them
- treat missing route metadata and missing objects as different failure modes

## Cache Guidance

- HTML: short TTL
- route metadata: short TTL
- hashed assets: `public, max-age=31536000, immutable`

## Tests

Cover:

- hostname resolution on cache miss
- short-TTL cache refresh behavior
- immutable asset cache headers
- not-found behavior for route vs asset
- rollback behavior when route resolution changes
