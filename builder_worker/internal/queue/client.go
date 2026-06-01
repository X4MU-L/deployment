package queue

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"builder_worker/internal/logger"
)

type Config struct {
	APIBaseURL string
	AccountID  string
	APIToken   string
	QueueID    string
}

type PulledMessage struct {
	Body        string         `json:"body"`
	ID          string         `json:"id"`
	TimestampMS int64          `json:"timestamp_ms"`
	Attempts    int            `json:"attempts"`
	LeaseID     string         `json:"lease_id"`
	Metadata    map[string]any `json:"metadata"`
}

func (m PulledMessage) ContentType() string {
	if m.Metadata == nil {
		return "json"
	}
	if contentType, ok := m.Metadata["CF-Content-Type"].(string); ok && contentType != "" {
		return contentType
	}
	return "json"
}

func (m PulledMessage) DecodeJSON(target any) error {
	if m.ContentType() == "text" {
		return json.Unmarshal([]byte(m.Body), target)
	}

	if m.ContentType() != "json" {
		return fmt.Errorf("unsupported queue content type: %s", m.ContentType())
	}

	if err := json.Unmarshal([]byte(m.Body), target); err == nil {
		return nil
	}

	decoded, err := base64.StdEncoding.DecodeString(m.Body)
	if err != nil {
		return fmt.Errorf("decode queue body: %w", err)
	}
	if err := json.Unmarshal(decoded, target); err != nil {
		return fmt.Errorf("unmarshal queue body: %w", err)
	}
	return nil
}

type Client interface {
	PullMessages(ctx context.Context, batchSize int, visibilityTimeoutMS int) ([]PulledMessage, error)
	Acknowledge(ctx context.Context, acks []string, retries []string) error
}

type HTTPClient struct {
	config     Config
	httpClient *http.Client
}

func NewHTTPClient(config Config) *HTTPClient {
	return &HTTPClient{
		config: config,
		httpClient: &http.Client{
			Timeout: 15 * time.Second,
		},
	}
}

func (c *HTTPClient) PullMessages(ctx context.Context, batchSize int, visibilityTimeoutMS int) ([]PulledMessage, error) {
	payload := map[string]any{
		"batch_size":            batchSize,
		"visibility_timeout_ms": visibilityTimeoutMS,
	}
	var response struct {
		Success bool `json:"success"`
		Result  struct {
			Messages []PulledMessage `json:"messages"`
		} `json:"result"`
	}
	if err := c.post(ctx, "messages/pull", payload, &response); err != nil {
		return nil, err
	}
	if !response.Success {
		return nil, fmt.Errorf("cloudflare queue pull failed")
	}
	logger.Debug(
		"queue pull completed",
		"batch_size",
		batchSize,
		"visibility_timeout_ms",
		visibilityTimeoutMS,
		"received",
		len(response.Result.Messages),
	)
	for _, message := range response.Result.Messages {
		logger.Debug(
			"queue message received",
			"message_id",
			message.ID,
			"lease_id",
			message.LeaseID,
			"attempts",
			message.Attempts,
			"content_type",
			message.ContentType(),
			"timestamp_ms",
			message.TimestampMS,
		)
	}
	return response.Result.Messages, nil
}

func (c *HTTPClient) Acknowledge(ctx context.Context, acks []string, retries []string) error {
	payload := map[string]any{
		"acks":    leaseIDsToPayload(acks),
		"retries": leaseIDsToPayload(retries),
	}
	var response struct {
		Success bool `json:"success"`
	}
	if err := c.post(ctx, "messages/ack", payload, &response); err != nil {
		return err
	}
	if !response.Success {
		return fmt.Errorf("cloudflare queue ack failed")
	}
	logger.Info(
		"queue acknowledge completed",
		"ack_count",
		len(acks),
		"retry_count",
		len(retries),
	)
	return nil
}

func leaseIDsToPayload(leaseIDs []string) []map[string]string {
	result := make([]map[string]string, 0, len(leaseIDs))
	for _, leaseID := range leaseIDs {
		result = append(result, map[string]string{"lease_id": leaseID})
	}
	return result
}

func (c *HTTPClient) post(ctx context.Context, suffix string, payload any, target any) error {
	if c.config.AccountID == "" || c.config.APIToken == "" || c.config.QueueID == "" {
		return fmt.Errorf("cloudflare queue client is not configured")
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("marshal queue payload: %w", err)
	}

	url := fmt.Sprintf(
		"%s/accounts/%s/queues/%s/%s",
		strings.TrimRight(c.config.APIBaseURL, "/"),
		c.config.AccountID,
		c.config.QueueID,
		suffix,
	)
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("build queue request: %w", err)
	}
	request.Header.Set("Authorization", "Bearer "+c.config.APIToken)
	request.Header.Set("Content-Type", "application/json")

	start := time.Now()
	response, err := c.httpClient.Do(request)
	if err != nil {
		return fmt.Errorf("send queue request: %w", err)
	}
	defer response.Body.Close()

	logger.Debug(
		"queue request completed",
		"suffix",
		suffix,
		"status_code",
		response.StatusCode,
		"duration_ms",
		time.Since(start).Milliseconds(),
	)

	if response.StatusCode >= 400 {
		responseBody, _ := io.ReadAll(response.Body)
		return fmt.Errorf("queue request failed: status=%d body=%s", response.StatusCode, string(responseBody))
	}

	if err := json.NewDecoder(response.Body).Decode(target); err != nil {
		return fmt.Errorf("decode queue response: %w", err)
	}
	return nil
}
