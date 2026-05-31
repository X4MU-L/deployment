---
name: observability-correlation-slice
description: Use when adding or changing observability across the deployment platform, including correlation IDs, log event structure, request-to-job trace propagation, SSE log identifiers, and tests that verify cross-plane traceability.
---

# Observability Correlation Slice

## Purpose

Keep one workflow traceable across dashboard, control plane, builder, and later runtime services.

Use this when:

- introducing correlation IDs
- designing log chunk metadata
- propagating request identifiers into queue jobs
- validating SSE resume identifiers

## Default Pattern

- incoming request creates or adopts a `correlation_id`
- control plane stores it on build and release records
- queue messages carry it
- builder logs and status callbacks echo it
- SSE events expose stable event ids plus correlation context where useful

## Rules

- correlation IDs do not replace resource IDs such as `build_id`
- log stream event ids must be monotonic per stream
- tracing metadata must not leak secrets
- prefer structured logs over free-form parsing conventions

## Verification

For any new workflow, verify you can trace:

- trigger request
- build record
- queue message
- builder logs
- release activation
