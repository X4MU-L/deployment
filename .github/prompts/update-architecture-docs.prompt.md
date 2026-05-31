---
description: "Update deployment architecture docs: service boundaries, flows, mermaid diagrams, and v1 decisions."
name: "Update Architecture Docs"
argument-hint: "What changed? (service/flow/contract/decision)"
agent: "Platform Architecture (Docs)"
---
Update the relevant docs under `deployment/` to reflect the requested change.

Requirements:
- Keep scope v1-minimal; label v2 ideas explicitly.
- Update Mermaid diagrams if flows/state machines change.
- Keep terminology consistent (control/build/runtime/routing/edge planes).
- Link to reference code paths in this workspace when patterns already exist (e.g., `ngrok_alternative/control_plane/...`, `ngrok_alternative/data_plane/...`, `fasttunnel-cli-extract/...`).
- If navigation changes, update `litile_overview.md`.

Output:
- List files changed
- Short summary of the updated design
- Any open questions/decisions left unresolved
