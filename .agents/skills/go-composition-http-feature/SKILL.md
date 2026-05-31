---
name: go-composition-http-feature
description: Use when adding or changing a Go HTTP feature using composition-first design: handlers, services, small interfaces, constructor injection, request parsing, response helpers, context propagation, and table-driven tests.
---

# Go Composition HTTP Feature

## Purpose

Add HTTP behavior in Go without letting handlers become business logic containers.

Use this when:

- Adding a REST endpoint.
- Adding an internal service-to-service handler.
- Refactoring handler logic into services.
- Adding testable dependencies around storage, auth, routing, or clients.

## First Questions

- What package should own this behavior?
- Is this transport-only logic or domain/business logic?
- What dependencies does it need: verifier, repository, registry, router, client, logger, clock?
- Which dependencies should be interfaces owned by the consumer package?
- How does cancellation flow?
- What error responses are stable for callers?

## Package Shape

Prefer focused packages:

```text
cmd/<app>/main.go       # wiring only
internal/<feature>/     # behavior
internal/httputil/      # shared response helpers when present
```

`cmd` should construct config, dependencies, handlers, and servers. Keep real behavior in `internal`.

## Handler Pattern

```go
type Handler struct {
    service *Service
}

func NewHandler(service *Service) *Handler {
    return &Handler{service: service}
}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
    if r.Method != http.MethodPost {
        writeError(w, http.StatusMethodNotAllowed, "method not allowed")
        return
    }

    var payload request
    if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
        writeError(w, http.StatusBadRequest, "invalid JSON body")
        return
    }

    result, err := h.service.Do(r.Context(), payload.Value)
    if err != nil {
        ...
        return
    }

    writeJSON(w, http.StatusOK, result)
}
```

Keep request/response structs private unless another package must use them.

## Service and Interface Pattern

Use small consumer-owned interfaces:

```go
type Store interface {
    Get(ctx context.Context, id string) (Record, error)
}

type Service struct {
    store Store
}

func NewService(store Store) *Service {
    return &Service{store: store}
}
```

Avoid package-wide globals. Avoid broad interfaces that mimic entire clients.

## Context and Errors

- Pass `r.Context()` downward.
- Do not store request contexts on structs.
- Return errors with context: `fmt.Errorf("load thing: %w", err)`.
- Map domain errors to HTTP status at the handler boundary.
- Log only where the error is handled or intentionally swallowed.

## Tests

Use table-driven tests with `httptest`.

Cover:

- Method not allowed.
- Invalid JSON.
- Missing required fields.
- Auth failure if relevant.
- Service error mapping.
- Happy path status/body.
- Context cancellation when behavior is long-running.

Run:

```bash
go test ./...
gofmt -w <changed-go-files>
```
