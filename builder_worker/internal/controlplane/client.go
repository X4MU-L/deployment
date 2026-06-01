package controlplane

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

type Client struct {
	baseURL      string
	serviceToken string
	serviceName  string
	httpClient   *http.Client
}

func NewClient(baseURL string, serviceToken string, serviceName string) *Client {
	return &Client{
		baseURL:      strings.TrimRight(baseURL, "/"),
		serviceToken: serviceToken,
		serviceName:  serviceName,
		httpClient: &http.Client{
			Timeout: 15 * time.Second,
		},
	}
}

type BuildResponse struct {
	ID               string         `json:"id"`
	ProjectID        string         `json:"project_id"`
	PlannedReleaseID string         `json:"planned_release_id"`
	Status           string         `json:"status"`
	SourceRef        string         `json:"source_ref"`
	SourceSnapshot   map[string]any `json:"source_snapshot"`
	BuildConfig      map[string]any `json:"build_config"`
}

type BuildClaimRequest struct {
	LeaseSeconds int `json:"lease_seconds"`
}

type BuildClaimResponse struct {
	Claimed bool          `json:"claimed"`
	Reason  string        `json:"reason"`
	Build   BuildResponse `json:"build"`
}

type BuildStatusUpdateRequest struct {
	Status       string `json:"status"`
	ArtifactRef  string `json:"artifact_ref,omitempty"`
	ErrorMessage string `json:"error_message,omitempty"`
}

type BuildLogIngestRequest struct {
	Stream   string   `json:"stream"`
	Lines    []string `json:"lines"`
	StartSeq int      `json:"start_seq"`
}

type BuildCompleteRequest struct {
	Status       string `json:"status"`
	ArtifactRef  string `json:"artifact_ref,omitempty"`
	ManifestRef  string `json:"manifest_ref,omitempty"`
	ErrorMessage string `json:"error_message,omitempty"`
}

func (c *Client) GetBuild(ctx context.Context, buildID string) (BuildResponse, error) {
	var build BuildResponse
	err := c.doJSON(ctx, http.MethodGet, fmt.Sprintf("/api/v1/internal/builds/%s", buildID), nil, &build)
	return build, err
}

func (c *Client) ClaimBuild(ctx context.Context, buildID string, request BuildClaimRequest) (BuildClaimResponse, error) {
	var response BuildClaimResponse
	err := c.doJSON(ctx, http.MethodPost, fmt.Sprintf("/api/v1/internal/builds/%s/claim", buildID), request, &response)
	return response, err
}

func (c *Client) UpdateBuildStatus(ctx context.Context, buildID string, request BuildStatusUpdateRequest) error {
	return c.doJSON(ctx, http.MethodPost, fmt.Sprintf("/api/v1/internal/builds/%s/status", buildID), request, nil)
}

func (c *Client) IngestBuildLogs(ctx context.Context, buildID string, request BuildLogIngestRequest) error {
	return c.doJSON(ctx, http.MethodPost, fmt.Sprintf("/api/v1/internal/builds/%s/logs", buildID), request, nil)
}

func (c *Client) CompleteBuild(ctx context.Context, buildID string, request BuildCompleteRequest) error {
	return c.doJSON(ctx, http.MethodPost, fmt.Sprintf("/api/v1/internal/builds/%s/complete", buildID), request, nil)
}

func (c *Client) doJSON(ctx context.Context, method string, path string, payload any, target any) error {
	var body io.Reader
	if payload != nil {
		encoded, err := json.Marshal(payload)
		if err != nil {
			return fmt.Errorf("marshal request payload: %w", err)
		}
		body = bytes.NewReader(encoded)
	}

	request, err := http.NewRequestWithContext(ctx, method, c.baseURL+path, body)
	if err != nil {
		return fmt.Errorf("build request: %w", err)
	}
	request.Header.Set("Authorization", "Bearer "+c.serviceToken)
	request.Header.Set("X-Service-Name", c.serviceName)
	if payload != nil {
		request.Header.Set("Content-Type", "application/json")
	}

	response, err := c.httpClient.Do(request)
	if err != nil {
		return fmt.Errorf("send request: %w", err)
	}
	defer response.Body.Close()

	if response.StatusCode >= 400 {
		responseBody, _ := io.ReadAll(response.Body)
		return fmt.Errorf("control plane request failed: status=%d body=%s", response.StatusCode, string(responseBody))
	}

	if target == nil {
		return nil
	}
	if err := json.NewDecoder(response.Body).Decode(target); err != nil {
		return fmt.Errorf("decode response: %w", err)
	}
	return nil
}
