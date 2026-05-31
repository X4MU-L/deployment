# Routing Plane (Wildcard Domains + Request Routing)

The routing plane decides what a wildcard hostname should serve.

For the initial product, routing is intentionally narrow:

- serve **static releases** through a Worker
- keep **container proxying** for the later runtime milestone

## Domain Layout

- Dashboard: `example.com` / `www.example.com`
- API: `api.example.com`
- Apps: `*.apps.example.com`

## Initial Product Strategy: Worker-First Static Routing

Bind a Worker route:

- `*.apps.example.com/*`

The Worker:

1. extracts the hostname
2. resolves the active route from the control plane on cache miss
3. serves static files from R2 using the returned manifest and release metadata

## Route Resolution

The source of truth is:

- `GET /internal/routes/resolve?hostname=...`

The control plane returns:

- `route_kind`
- `release_id`
- `cache_ttl_seconds`
- `invalidation_version`
- R2 bucket/prefix and manifest pointer

See [platform-contracts.md](../platform-contracts.md) for the frozen response contract.

## Worker Caching Model

Recommended behavior:

- cache route resolution for a short TTL
- cache immutable assets aggressively
- keep HTML and route metadata short-lived so rollback is fast

This gives:

- cheap repeat lookups at the edge
- controlled propagation time when routes change

## Static Asset Serving Rules

- hashed assets get long-lived immutable caching
- HTML should have short TTLs
- missing files should fail cleanly and not poison route cache

## Later Strategy: Container Traffic

After the runtime plane exists:

- the Worker remains the public front door
- static routes keep using R2 directly
- container routes forward to a stable origin router

Do not make the Worker own per-node runtime topology in the initial product.

## Alternative: Origin-First Routing

Origin-first routing remains a valid fallback if Worker routing proves operationally awkward.

However, the approved default is:

- Worker-first for static v1
- origin router behind the Worker for container traffic later

## Operational Notes

- SSE endpoints are not served through the wildcard routing Worker
- route resolution auth is service-to-service only
- Worker code must stream responses and avoid unnecessary buffering
