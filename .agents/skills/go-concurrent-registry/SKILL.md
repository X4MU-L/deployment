---
name: go-concurrent-registry
description: Use when implementing or changing an in-memory concurrent registry/table in Go: map ownership, sync.RWMutex, bind/resolve/unbind methods, close cleanup, lifecycle tests, and avoiding goroutine/channel leaks.
---

# Go Concurrent Registry

## Purpose

Build a small, safe in-memory registry for live process state such as sessions, routes, connections, subscriptions, workers, or leases.

Use this when:

- You need to bind an ID/name to runtime state.
- Multiple goroutines read and write a map.
- Entries need cleanup on disconnect or shutdown.
- Tests need deterministic state transitions.

## First Questions

- What is the registry key?
- What is the entry value?
- Who owns entry lifecycle and cleanup?
- Can a key be overwritten?
- Should lookup return a copy, pointer, or interface?
- What happens on unregister if the key does not exist?
- Does the registry need close-all shutdown behavior?

## Basic Pattern

```go
type Registry struct {
    mu      sync.RWMutex
    entries map[string]Entry
}

func NewRegistry() *Registry {
    return &Registry{entries: make(map[string]Entry)}
}

func (r *Registry) Register(key string, entry Entry) {
    r.mu.Lock()
    defer r.mu.Unlock()
    r.entries[key] = entry
}

func (r *Registry) Get(key string) (Entry, bool) {
    r.mu.RLock()
    defer r.mu.RUnlock()
    entry, ok := r.entries[key]
    return entry, ok
}

func (r *Registry) Unregister(key string) {
    r.mu.Lock()
    defer r.mu.Unlock()
    delete(r.entries, key)
}
```

## Entry Cleanup

If entries hold resources, remove under lock but close outside the lock:

```go
func (r *Registry) Remove(key string) (io.Closer, bool) {
    r.mu.Lock()
    entry, ok := r.entries[key]
    if ok {
        delete(r.entries, key)
    }
    r.mu.Unlock()
    return entry, ok
}
```

Then close after removal. This avoids blocking other registry users while cleanup runs.

## Channel and Goroutine Safety

- Use `sync.Once` for closeable channels owned by an entry.
- Do not close channels you do not own.
- Do not send on unbounded channels.
- Make goroutine shutdown explicit with `context.Context`, done channels, or owner `Close`.
- Add tests that prove blocked goroutines exit after close/cancel.

## API Design

Keep registry methods small and intention-revealing:

- `Bind(host, sessionID)`
- `Resolve(host)`
- `Unbind(host)`
- `Register(ctx, entry)`
- `GetByID(id)`
- `CloseAll()`

Avoid exposing the internal map. Avoid returning mutable shared entries unless callers need live state.

## Tests

Cover:

- Register/get.
- Overwrite behavior.
- Missing lookup.
- Remove/unregister.
- Close cleanup.
- Concurrent access with `go test -race` when possible.

Run:

```bash
go test ./...
go test -race ./...
gofmt -w <changed-go-files>
```
