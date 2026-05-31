---
description: "Use when editing deployment architecture docs: microservice boundaries, contracts, SSR/streaming vs SSE, queues, R2, routing. Keeps terminology and diagrams consistent."
applyTo: "**/*.md"
---
# Deployment Docs — Writing Rules

## Consistency
- Use consistent terms: **control plane**, **build plane**, **runtime plane**, **routing plane**, **edge plane**.
- Clearly label v1 decisions vs v2 ideas.

## Diagrams
- Prefer Mermaid for flows and state machines.
- Keep diagrams updated when changing flows.

## Structure
- Prefer short sections and bullet lists.
- When you add/remove a doc, update `litile_overview.md` so navigation stays correct.

## Write For Implementation
- Write docs so a coding agent can implement: include contracts (HTTP endpoints, queue event schemas, SSE event types), invariants (idempotency, at-least-once), and success criteria.
 - When a pattern exists in reference code in this workspace, link to the concrete path (e.g., `ngrok_alternative/control_plane/...`, `ngrok_alternative/data_plane/...`, `fasttunnel-cli-extract/...`).
 - Always label such links explicitly as "Reference implementation (read-only)" and place authoritative contracts and decisions in `deployment/`.

## Scope Control
- Don’t invent new components or “nice-to-haves” beyond the described v1.
- Default to the simplest interpretation that satisfies the current spec.
