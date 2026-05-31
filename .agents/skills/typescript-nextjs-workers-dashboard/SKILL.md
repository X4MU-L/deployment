---
name: typescript-nextjs-workers-dashboard
description: Use when creating or changing the dashboard on Cloudflare Workers with Next.js via OpenNext, including cookie auth redirects, SSR/streaming, same-origin SSE proxy routes, TanStack Query integration, and SSR-safe Zustand usage.
---

# Next.js Workers Dashboard

## Purpose

Build or change the operator dashboard for the deployment platform.

Use this when:

- adding dashboard routes or layouts
- implementing cookie-based auth on Workers
- adding same-origin SSE proxy endpoints
- wiring TanStack Query into SSR/client flows
- adding Zustand for transient UI state

## First Checks

- confirm the page belongs to the static-first product scope
- identify which control-plane endpoint owns the data
- confirm auth should happen before HTML is sent
- decide whether the work is server-rendered, client-only, or mixed

## Default Architecture

- Next.js on Workers via OpenNext
- server-side cookie auth and redirects
- TanStack Query for server state
- Zustand only for local UI state
- SSE proxied through same-origin Worker routes

## Implementation Rules

- keep page shells server-rendered by default
- do auth decisions on the server
- avoid direct browser calls to cross-origin control-plane SSE endpoints
- do not duplicate control-plane business logic in the dashboard
- never store per-request state in module scope

## SSE Proxy Pattern

Use dashboard routes such as:

- `/api/builds/:buildId/logs/stream`

The route should:

- validate the user session
- connect to the control-plane SSE endpoint
- forward `Last-Event-ID` when present
- stream the upstream body instead of buffering it

## Data Split

- TanStack Query: projects, builds, releases, route metadata
- Zustand: panel state, selected filters, UI toggles
- log lines: local append-only stream state unless a shared cache is clearly needed

## Tests

Cover:

- auth redirect behavior
- SSE proxy response headers and pass-through behavior
- server-rendered page shells
- client log viewer reconnection handling when feasible
