---
description: "Implement a Go service feature with constructor DI, small interfaces, tests, and golangci-lint compliance (data plane / builder / runner style)."
name: "Add Go Service Feature"
argument-hint: "Package/behavior change, inputs/outputs, concurrency needs"
agent: "Go Platform Services"
---
Implement the requested Go feature following workspace conventions.

Constraints:
- Composition-first: explicit constructors, no globals.
- Wrap errors with `%w` and add operation context.
- Own goroutine lifetimes (context/done + WaitGroup).
- Keep `cmd/` wiring minimal; place logic in `internal/` packages.

Deliverables:
- Code changes + colocated tests
- Brief rationale for interface boundaries
- Commands to validate (`go test ./...`, `golangci-lint run`) if you don’t run them
