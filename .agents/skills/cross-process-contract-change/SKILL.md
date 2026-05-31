---
name: cross-process-contract-change
description: Use when a change crosses service/process boundaries: REST contracts, JWT/session claims, WebSocket or message frames, callback APIs, event ingestion, shared env vars, deployment config, backwards compatibility, and multi-project verification.
---

# Cross Process Contract Change

## Purpose

Coordinate changes where one component produces data and another consumes it.

Use this when changing:

- REST request/response payloads.
- JWT/session claims.
- WebSocket or message frames.
- Queue message schemas and consumer semantics.
- Internal callbacks.
- Event ingestion schemas.
- Shared secrets, URLs, ports, domains, or env vars.
- CLI/server or edge/backend workflows.

## First Questions

- Who produces the contract?
- Who consumes it?
- Is it persisted or only runtime?
- Is it public, internal, or private to one deployment?
- Must old clients keep working?
- What is the rollout order?
- Does the contract include resumability, idempotency, or lease semantics?
- What tests must change in every touched component?

## Contract Inventory

Find all sides:

- Producer schema/DTO/model.
- Consumer schema/DTO/model.
- Client adapter.
- Server endpoint/handler.
- Auth/token generation and verification.
- Deployment vars and templates.
- Tests, fixtures, factories, and examples.
- Resume tokens, event ids, idempotency keys, and claim/lease endpoints when relevant.

Do not change one side and leave the other inferred.

## REST Contract Changes

- Prefer additive fields with defaults for compatibility.
- Keep JSON naming convention consistent.
- Update server request/response schemas.
- Update client DTOs.
- Update error decoding if the error shape changes.
- Add tests for omitted optional fields and new fields.

## Token or Claim Changes

- Update token creation and verification together.
- Check expiry, issuer/audience, subject, and custom claims.
- Add tests for missing, mismatched, expired, and valid tokens.
- Keep algorithms and key paths aligned with deployment config.
- Fail closed for production security-sensitive paths.

## Message or Frame Changes

- Update encode/decode definitions on every participant.
- Preserve correlation IDs such as request ID, stream ID, job ID, or trace ID.
- Add explicit handling for unknown versions/types.
- Include close/error frames when streams are bidirectional.
- Test cancellation, malformed messages, and normal close.

## Queue Contract Changes

- Keep queue payloads small and versioned.
- Document ack/retry assumptions and whether delivery is at-least-once.
- Define what makes processing idempotent.
- Spell out when a claim or lease is required to avoid duplicate heavy work.
- Update producer, consumer, fixtures, and integration tests together.

## SSE And Resume Changes

- Define the event `id` contract explicitly.
- Update producer and consumer handling of `Last-Event-ID`.
- Test replay after reconnect, not only happy-path live streaming.
- Keep event ordering and terminal status behavior explicit.

## Trigger And Callback Changes

- Define where `Idempotency-Key` is accepted and how duplicates are resolved.
- Keep callback contracts explicit about retry safety.
- Verify terminal callbacks are safe to repeat.

## Env and Deployment Changes

- Add application setting/default.
- Add non-secret deploy var or vault secret.
- Render it into config/env templates.
- Restart/reload affected services through handlers.
- Keep local/dev values usable.

## Verification Matrix

For every touched process, run its relevant tests. Examples:

```bash
pytest
go test ./...
ansible-playbook --syntax-check playbooks/site.yml
```

For lifecycle workflows, add or update an integration test that covers the complete producer-to-consumer path.
