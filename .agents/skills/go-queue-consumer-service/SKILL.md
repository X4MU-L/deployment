---
name: go-queue-consumer-service
description: Use when building or changing a long-running Go service that consumes external queue work, especially Cloudflare Queues pull consumers, including polling loops, visibility timeout handling, ack/retry behavior, backoff, graceful shutdown, idempotent processing, and tests.
---

# Go Queue Consumer Service

## Purpose

Implement long-running external consumers for queued work.

Use this when:

- building the static builder pull consumer
- adding polling loops around Cloudflare Queues
- handling retries, acking, and graceful shutdown

## Service Shape

Prefer:

- `cmd/<service>/main.go` for wiring
- `internal/consumer/` for poll + ack loop
- `internal/handler/` for per-message orchestration
- `internal/client/` for queue and control-plane adapters

## Poll Loop Rules

- poll in bounded batches
- make visibility timeout explicit
- separate retryable failures from terminal ones
- do not ack work before durable downstream state is updated
- apply backoff when the queue is empty or downstream systems are unhealthy

## Idempotency

- handlers must tolerate duplicate delivery
- use build or release identifiers as the control-plane source of truth
- keep heavy work behind a claim or lease when available

## Shutdown

- use `signal.NotifyContext`
- stop polling on cancellation
- let in-flight work finish or abandon intentionally
- avoid goroutine leaks in ticker or worker pools

## Tests

Cover:

- empty queue polling
- successful processing and ack
- retryable downstream failure
- malformed message handling
- cancellation during long-running processing
