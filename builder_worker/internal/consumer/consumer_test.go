package consumer

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"testing"

	"builder_worker/internal/contracts"
	"builder_worker/internal/queue"
)

func TestRunOnceAcknowledgesSuccessfulMessage(t *testing.T) {
	queueClient := &stubQueueClient{
		messages: []queue.PulledMessage{
			buildRequestedMessage(t, "lease-ok", 1),
		},
	}
	handler := &stubHandler{}
	consumer := New(Config{
		BatchSize:           5,
		VisibilityTimeoutMS: 30000,
		MaxAttempts:         3,
	}, queueClient, handler)

	processed, err := consumer.RunOnce(context.Background())
	if err != nil {
		t.Fatalf("RunOnce returned error: %v", err)
	}
	if processed != 1 {
		t.Fatalf("expected 1 processed message, got %d", processed)
	}
	if len(handler.handledBuildIDs) != 1 || handler.handledBuildIDs[0] != "build-1" {
		t.Fatalf("unexpected handled build ids: %#v", handler.handledBuildIDs)
	}
	if len(queueClient.ackLeaseIDs) != 1 || queueClient.ackLeaseIDs[0] != "lease-ok" {
		t.Fatalf("unexpected ack lease ids: %#v", queueClient.ackLeaseIDs)
	}
	if len(queueClient.retryLeaseIDs) != 0 {
		t.Fatalf("unexpected retry lease ids: %#v", queueClient.retryLeaseIDs)
	}
}

func TestRunOnceRetriesTransientHandlerFailure(t *testing.T) {
	queueClient := &stubQueueClient{
		messages: []queue.PulledMessage{
			buildRequestedMessage(t, "lease-retry", 1),
		},
	}
	handler := &stubHandler{err: errors.New("temporary downstream failure")}
	consumer := New(Config{
		BatchSize:           5,
		VisibilityTimeoutMS: 30000,
		MaxAttempts:         3,
	}, queueClient, handler)

	processed, err := consumer.RunOnce(context.Background())
	if err != nil {
		t.Fatalf("RunOnce returned error: %v", err)
	}
	if processed != 1 {
		t.Fatalf("expected 1 processed message, got %d", processed)
	}
	if len(queueClient.retryLeaseIDs) != 1 || queueClient.retryLeaseIDs[0] != "lease-retry" {
		t.Fatalf("unexpected retry lease ids: %#v", queueClient.retryLeaseIDs)
	}
	if len(queueClient.ackLeaseIDs) != 0 {
		t.Fatalf("unexpected ack lease ids: %#v", queueClient.ackLeaseIDs)
	}
}

func TestRunOnceAcknowledgesTerminalHandlerFailure(t *testing.T) {
	queueClient := &stubQueueClient{
		messages: []queue.PulledMessage{
			buildRequestedMessage(t, "lease-terminal", 1),
		},
	}
	handler := &stubHandler{err: TerminalError(errors.New("unsupported source"))}
	consumer := New(Config{
		BatchSize:           5,
		VisibilityTimeoutMS: 30000,
		MaxAttempts:         3,
	}, queueClient, handler)

	processed, err := consumer.RunOnce(context.Background())
	if err != nil {
		t.Fatalf("RunOnce returned error: %v", err)
	}
	if processed != 1 {
		t.Fatalf("expected 1 processed message, got %d", processed)
	}
	if len(queueClient.ackLeaseIDs) != 1 || queueClient.ackLeaseIDs[0] != "lease-terminal" {
		t.Fatalf("unexpected ack lease ids: %#v", queueClient.ackLeaseIDs)
	}
	if len(queueClient.retryLeaseIDs) != 0 {
		t.Fatalf("unexpected retry lease ids: %#v", queueClient.retryLeaseIDs)
	}
}

func TestRunOnceAcknowledgesMalformedMessage(t *testing.T) {
	queueClient := &stubQueueClient{
		messages: []queue.PulledMessage{
			{
				Body:        "!!!bad!!!",
				ID:          "msg-bad",
				TimestampMS: 1710950954154,
				Attempts:    1,
				LeaseID:     "lease-bad",
				Metadata:    map[string]any{"CF-Content-Type": "json"},
			},
		},
	}
	handler := &stubHandler{}
	consumer := New(Config{
		BatchSize:           5,
		VisibilityTimeoutMS: 30000,
		MaxAttempts:         3,
	}, queueClient, handler)

	processed, err := consumer.RunOnce(context.Background())
	if err != nil {
		t.Fatalf("RunOnce returned error: %v", err)
	}
	if processed != 1 {
		t.Fatalf("expected 1 processed message, got %d", processed)
	}
	if len(handler.handledBuildIDs) != 0 {
		t.Fatalf("malformed message should not reach handler: %#v", handler.handledBuildIDs)
	}
	if len(queueClient.ackLeaseIDs) != 1 || queueClient.ackLeaseIDs[0] != "lease-bad" {
		t.Fatalf("unexpected ack lease ids: %#v", queueClient.ackLeaseIDs)
	}
}

func TestRunOnceAcknowledgesMessageAtMaxAttempts(t *testing.T) {
	queueClient := &stubQueueClient{
		messages: []queue.PulledMessage{
			buildRequestedMessage(t, "lease-final", 3),
		},
	}
	handler := &stubHandler{err: errors.New("still failing")}
	consumer := New(Config{
		BatchSize:           5,
		VisibilityTimeoutMS: 30000,
		MaxAttempts:         3,
	}, queueClient, handler)

	processed, err := consumer.RunOnce(context.Background())
	if err != nil {
		t.Fatalf("RunOnce returned error: %v", err)
	}
	if processed != 1 {
		t.Fatalf("expected 1 processed message, got %d", processed)
	}
	if len(queueClient.ackLeaseIDs) != 1 || queueClient.ackLeaseIDs[0] != "lease-final" {
		t.Fatalf("unexpected ack lease ids: %#v", queueClient.ackLeaseIDs)
	}
	if len(queueClient.retryLeaseIDs) != 0 {
		t.Fatalf("unexpected retry lease ids: %#v", queueClient.retryLeaseIDs)
	}
}

type stubQueueClient struct {
	messages      []queue.PulledMessage
	ackLeaseIDs   []string
	retryLeaseIDs []string
}

func (s *stubQueueClient) PullMessages(_ context.Context, _ int, _ int) ([]queue.PulledMessage, error) {
	return s.messages, nil
}

func (s *stubQueueClient) Acknowledge(_ context.Context, acks []string, retries []string) error {
	s.ackLeaseIDs = append([]string{}, acks...)
	s.retryLeaseIDs = append([]string{}, retries...)
	return nil
}

type stubHandler struct {
	err             error
	handledBuildIDs []string
}

func (s *stubHandler) Handle(_ context.Context, message contracts.BuildRequestedMessage) error {
	s.handledBuildIDs = append(s.handledBuildIDs, message.BuildID)
	return s.err
}

func buildRequestedMessage(t *testing.T, leaseID string, attempts int) queue.PulledMessage {
	t.Helper()
	payload := map[string]any{
		"schema":         "build.requested.v1",
		"build_id":       "build-1",
		"project_id":     "project-1",
		"environment_id": "env-1",
		"release_id":     "release-1",
		"correlation_id": "corr-1",
		"attempt":        1,
		"git_checkout": map[string]any{
			"repo_url": "https://github.com/example/demo",
		},
		"build_spec": map[string]any{
			"kind": "static",
		},
		"artifact_target": map[string]any{
			"provider":     "r2",
			"bucket":       "static-artifacts",
			"prefix":       "projects/project-1/releases/release-1",
			"manifest_key": "projects/project-1/releases/release-1/static_release_manifest.v1.json",
		},
	}
	encoded, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal payload: %v", err)
	}
	return queue.PulledMessage{
		Body:        base64.StdEncoding.EncodeToString(encoded),
		ID:          "msg-" + leaseID,
		TimestampMS: 1710950954154,
		Attempts:    attempts,
		LeaseID:     leaseID,
		Metadata:    map[string]any{"CF-Content-Type": "json"},
	}
}
