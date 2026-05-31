# Project Guidelines — Deployment Docs (Architecture)

## Purpose
- This folder is the **architecture/design source** for the deployment platform (Cloudflare + self-hosted control/build/runtime planes).
- Prefer clear service boundaries and **explicit contracts**; include enough detail that a coding agent can implement and test the system.
- When a pattern already exists in this workspace (FastTunnel control/data plane, CLI, infra), link to the concrete file paths instead of inventing new conventions.

Canonical reference: `engineering-standards.md`.

## Docs Style
- Keep docs concise and scannable.
- Use consistent vocabulary: control plane, build plane, runtime plane, routing plane, edge plane.
- Prefer Mermaid diagrams for flows/state machines.
- When updating docs, also update the index in `litile_overview.md` if it changes navigation.

## Decisions (Current)
- First sellable product is static deploys only.
- Container runtime remains a later milestone, not equal day-one scope.
- Control plane stays Python (FastAPI) with Postgres as canonical state.
- Build/runtime services stay Go; queue consumption and build execution belong there.
- Dashboard is TypeScript + Next.js on Cloudflare Workers via OpenNext (v1).
- Worker-first routing is the default for static apps; container traffic uses a stable origin router later.
- Redis is not part of the initial product critical path.
- Composition over inheritance is a project-wide rule; use classes only for lifecycle-managed collaborators.
