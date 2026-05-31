# Client Dashboard (Framework + Data Fetching)

The dashboard is the operator-facing control surface for the platform.

For the approved initial product, the dashboard only needs to support the **static deploy path**:

- create projects
- trigger static builds
- watch build logs
- inspect releases and routes

## Framework Decision

The framework choice is now frozen for the first product:

- **Next.js on Cloudflare Workers via OpenNext**

This gives the project:

- SSR and streaming for operator pages
- server-side redirects for cookie auth
- a same-origin home for the SSE proxy layer

## What The Dashboard Should Not Own

- direct access to Cloudflare Queues
- direct route truth
- direct artifact management in R2
- build orchestration logic that belongs in the control plane

The dashboard is a client of the control plane and a proxy for authenticated streaming.

## Rendering Modes

Use a mixed model:

- **SSR** for authenticated page shells and first-load status
- **Streaming** for slow sections
- **Client rendering** for live log panes and highly interactive filters

## Auth

Default model:

- secure cookie session
- server-side auth checks
- redirect before HTML is sent

This avoids login flicker and keeps the dashboard aligned with Worker-based SSR.

## Data Fetching

Preferred split:

- **TanStack Query** for server state
- **Zustand** for transient UI state

Do not duplicate server state in Zustand.

## SSE Log Viewer Pattern

Recommended path:

- browser connects to a dashboard endpoint like `/api/builds/:buildId/logs/stream`
- dashboard route proxies the control-plane SSE stream
- reconnection uses `Last-Event-ID`

This keeps auth, cookies, and browser behavior same-origin.

## Initial Product Screens

The first dashboard milestone should cover:

- project list/create
- project detail
- build trigger view
- build detail with live logs
- release detail with route metadata

Container runtime views are not part of the first product.

## Future Expansion

After the static path is stable, the dashboard can grow into:

- container deployment views
- runtime health views
- preview environments
- custom-domain workflows

Those should be layered onto stable control-plane contracts, not invented in the UI first.
