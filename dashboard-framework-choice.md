# Dashboard Framework Choice: Next.js vs TanStack Start

This comparison remains useful as background, but the v1 decision is now frozen.

## Decision

For the first product, choose:

- **Next.js on Cloudflare Workers via OpenNext**

Reason:

- strongest SSR and auth conventions
- mature enough for Worker-based dashboard deployment
- easy fit for a same-origin SSE proxy layer

## Why Not Re-open The Choice Now

The project already has enough uncertainty in:

- build orchestration
- route resolution
- R2 artifact serving
- resumable log streaming

Re-opening the framework choice adds risk without helping the first product ship sooner.

## When To Re-evaluate

Revisit TanStack Start only if one of these becomes true:

- the team strongly prefers TanStack Router conventions everywhere
- Worker deployment constraints create friction specific to Next.js
- a future dashboard rewrite is already justified for broader reasons

Until then, treat the framework decision as settled.
