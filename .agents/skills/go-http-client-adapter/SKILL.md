---
name: go-http-client-adapter
description: Use when adding a Go HTTP client adapter for calling another service: typed request/response DTOs, auth headers, context-aware requests, timeouts, error wrapping, response validation, and httptest coverage.
---

# Go HTTP Client Adapter

## Purpose

Create a small typed client for service-to-service calls without leaking HTTP details throughout the codebase.

Use this when:

- A Go service needs to call another HTTP API.
- A CLI needs to call a backend.
- An edge/service process needs callback or event publishing behavior.

## First Questions

- What operation is being called?
- Is the call required or best-effort?
- What auth headers or tokens are needed?
- What timeout is appropriate?
- What status codes are success?
- What error body format should be decoded?
- Does the method need retries or batching?

## Client Shape

```go
type Client struct {
    baseURL string
    token   string
    http    *http.Client
}

func New(baseURL, token string) *Client {
    return &Client{
        baseURL: strings.TrimRight(baseURL, "/"),
        token: token,
        http: &http.Client{Timeout: 5 * time.Second},
    }
}
```

Allow injecting `*http.Client` if tests or callers need custom transports.

## Method Pattern

```go
func (c *Client) CreateThing(ctx context.Context, payload CreateThingRequest) (ThingResponse, error) {
    body, err := json.Marshal(payload)
    if err != nil {
        return ThingResponse{}, fmt.Errorf("marshal create thing request: %w", err)
    }

    req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/things", bytes.NewReader(body))
    if err != nil {
        return ThingResponse{}, fmt.Errorf("build create thing request: %w", err)
    }
    req.Header.Set("Content-Type", "application/json")
    if c.token != "" {
        req.Header.Set("Authorization", "Bearer "+c.token)
    }

    resp, err := c.http.Do(req)
    if err != nil {
        return ThingResponse{}, fmt.Errorf("send create thing request: %w", err)
    }
    defer resp.Body.Close()

    if resp.StatusCode >= 300 {
        return ThingResponse{}, decodeAPIError(resp)
    }

    var out ThingResponse
    if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
        return ThingResponse{}, fmt.Errorf("decode create thing response: %w", err)
    }
    return out, nil
}
```

## Error Handling

- Wrap network/build/decode errors with operation context.
- Decode API error bodies when the remote service has a stable error shape.
- Include status code in errors for non-2xx responses.
- For best-effort cleanup notifications, log and return only if the caller can act.

## Tests

Use `httptest.Server`.

Cover:

- Request method/path/body.
- Auth headers.
- Success decode.
- Non-2xx error.
- Malformed response body.
- Context cancellation or timeout when practical.

Run:

```bash
go test ./...
gofmt -w <changed-go-files>
```
