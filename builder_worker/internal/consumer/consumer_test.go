package consumer

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"slices"
	"sync"
	"testing"
	"time"

	"builder_worker/internal/contracts"
	"builder_worker/internal/queue"
)

func TestRunOnceAcknowledgesSuccessfulMessage(t *testing.T) {
	queueClient := &stubQueueClient{
		pulls: [][]queue.PulledMessage{{
			buildRequestedMessage(t, "lease-ok", 1),
		}},
	}
	handler := &stubHandler{}
	consumer := New(Config{
		BatchSize:           5,
		VisibilityTimeoutMS: 30000,
		MaxAttempts:         3,
		MaxConcurrentBuilds: 2,
	}, queueClient, handler)

	runUntilSettled(t, consumer, 4)
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
		pulls: [][]queue.PulledMessage{{
			buildRequestedMessage(t, "lease-retry", 1),
		}},
	}
	handler := &stubHandler{err: errors.New("temporary downstream failure")}
	consumer := New(Config{
		BatchSize:           5,
		VisibilityTimeoutMS: 30000,
		MaxAttempts:         3,
		MaxConcurrentBuilds: 2,
	}, queueClient, handler)

	runUntilSettled(t, consumer, 4)
	if len(queueClient.retryLeaseIDs) != 1 || queueClient.retryLeaseIDs[0] != "lease-retry" {
		t.Fatalf("unexpected retry lease ids: %#v", queueClient.retryLeaseIDs)
	}
	if len(queueClient.ackLeaseIDs) != 0 {
		t.Fatalf("unexpected ack lease ids: %#v", queueClient.ackLeaseIDs)
	}
}

func TestRunOnceAcknowledgesTerminalHandlerFailure(t *testing.T) {
	queueClient := &stubQueueClient{
		pulls: [][]queue.PulledMessage{{
			buildRequestedMessage(t, "lease-terminal", 1),
		}},
	}
	handler := &stubHandler{err: TerminalError(errors.New("unsupported source"))}
	consumer := New(Config{
		BatchSize:           5,
		VisibilityTimeoutMS: 30000,
		MaxAttempts:         3,
		MaxConcurrentBuilds: 2,
	}, queueClient, handler)

	runUntilSettled(t, consumer, 4)
	if len(queueClient.ackLeaseIDs) != 1 || queueClient.ackLeaseIDs[0] != "lease-terminal" {
		t.Fatalf("unexpected ack lease ids: %#v", queueClient.ackLeaseIDs)
	}
	if len(queueClient.retryLeaseIDs) != 0 {
		t.Fatalf("unexpected retry lease ids: %#v", queueClient.retryLeaseIDs)
	}
}

func TestRunOnceAcknowledgesMalformedMessage(t *testing.T) {
	queueClient := &stubQueueClient{
		pulls: [][]queue.PulledMessage{{
			{
				Body:        "!!!bad!!!",
				ID:          "msg-bad",
				TimestampMS: 1710950954154,
				Attempts:    1,
				LeaseID:     "lease-bad",
				Metadata:    map[string]any{"CF-Content-Type": "json"},
			},
		}},
	}
	handler := &stubHandler{}
	consumer := New(Config{
		BatchSize:           5,
		VisibilityTimeoutMS: 30000,
		MaxAttempts:         3,
		MaxConcurrentBuilds: 2,
	}, queueClient, handler)

	runUntilSettled(t, consumer, 4)
	if len(handler.handledBuildIDs) != 0 {
		t.Fatalf("malformed message should not reach handler: %#v", handler.handledBuildIDs)
	}
	if len(queueClient.ackLeaseIDs) != 1 || queueClient.ackLeaseIDs[0] != "lease-bad" {
		t.Fatalf("unexpected ack lease ids: %#v", queueClient.ackLeaseIDs)
	}
}

func TestRunOnceAcknowledgesMessageAtMaxAttempts(t *testing.T) {
	queueClient := &stubQueueClient{
		pulls: [][]queue.PulledMessage{{
			buildRequestedMessage(t, "lease-final", 3),
		}},
	}
	handler := &stubHandler{err: errors.New("still failing")}
	consumer := New(Config{
		BatchSize:           5,
		VisibilityTimeoutMS: 30000,
		MaxAttempts:         3,
		MaxConcurrentBuilds: 2,
	}, queueClient, handler)

	runUntilSettled(t, consumer, 4)
	if len(queueClient.ackLeaseIDs) != 1 || queueClient.ackLeaseIDs[0] != "lease-final" {
		t.Fatalf("unexpected ack lease ids: %#v", queueClient.ackLeaseIDs)
	}
	if len(queueClient.retryLeaseIDs) != 0 {
		t.Fatalf("unexpected retry lease ids: %#v", queueClient.retryLeaseIDs)
	}
}

func TestRunOnceProcessesMixedBatchOutcomesInParallel(t *testing.T) {
	queueClient := &stubQueueClient{
		messages: []queue.PulledMessage{
			buildRequestedMessageWithBuildID(t, "lease-ok", 1, "build-ok"),
			buildRequestedMessageWithBuildID(t, "lease-retry", 1, "build-retry"),
			buildRequestedMessageWithBuildID(t, "lease-terminal", 1, "build-terminal"),
		},
	}
	handler := &mapHandler{
		errs: map[string]error{
			"build-retry":    errors.New("temporary downstream failure"),
			"build-terminal": TerminalError(errors.New("unsupported source")),
		},
	}
	consumer := New(Config{
		BatchSize:           5,
		VisibilityTimeoutMS: 30000,
		MaxAttempts:         3,
		MaxConcurrentBuilds: 3,
	}, queueClient, handler)

	runUntilSettled(t, consumer, 4)
	if !slices.Equal(sortedCopy(queueClient.ackLeaseIDs), []string{"lease-ok", "lease-terminal"}) {
		t.Fatalf("unexpected ack lease ids: %#v", queueClient.ackLeaseIDs)
	}
	if len(queueClient.retryLeaseIDs) != 1 || queueClient.retryLeaseIDs[0] != "lease-retry" {
		t.Fatalf("unexpected retry lease ids: %#v", queueClient.retryLeaseIDs)
	}
}

func TestRunOnceRespectsMaxConcurrentBuilds(t *testing.T) {
	queueClient := &stubQueueClient{
		messages: []queue.PulledMessage{
			buildRequestedMessageWithBuildID(t, "lease-1", 1, "build-1"),
			buildRequestedMessageWithBuildID(t, "lease-2", 1, "build-2"),
			buildRequestedMessageWithBuildID(t, "lease-3", 1, "build-3"),
		},
	}
	handler := newBlockingHandler()
	consumer := New(Config{
		BatchSize:           5,
		VisibilityTimeoutMS: 30000,
		MaxAttempts:         3,
		MaxConcurrentBuilds: 2,
	}, queueClient, handler)

	activity, err := consumer.RunOnce(context.Background())
	if err != nil {
		t.Fatalf("RunOnce returned error: %v", err)
	}
	if activity != 2 {
		t.Fatalf("expected first RunOnce to submit two builds, got %d", activity)
	}

	for i := 0; i < 2; i++ {
		select {
		case <-handler.started:
		case <-time.After(2 * time.Second):
			t.Fatalf("timed out waiting for handler start %d", i+1)
		}
	}

	select {
	case <-handler.started:
		t.Fatalf("third build should not start before capacity is released")
	case <-time.After(100 * time.Millisecond):
	}

	close(handler.release)
	runUntilSettled(t, consumer, 6)

	if handler.maxObserved != 2 {
		t.Fatalf("expected max observed concurrency 2, got %d", handler.maxObserved)
	}
	if len(queueClient.ackLeaseIDs) != 3 {
		t.Fatalf("expected all messages to be acknowledged, got %#v", queueClient.ackLeaseIDs)
	}
}

func TestRunOnceCanPullMoreWorkWhileEarlierBuildIsStillInFlight(t *testing.T) {
	queueClient := &stubQueueClient{
		pulls: [][]queue.PulledMessage{
			{buildRequestedMessageWithBuildID(t, "lease-1", 1, "build-1")},
			{buildRequestedMessageWithBuildID(t, "lease-2", 1, "build-2")},
		},
	}
	handler := newSelectiveBlockingHandler("build-1")
	consumer := New(Config{
		BatchSize:           5,
		VisibilityTimeoutMS: 30000,
		MaxAttempts:         3,
		MaxConcurrentBuilds: 2,
	}, queueClient, handler)

	activity, err := consumer.RunOnce(context.Background())
	if err != nil {
		t.Fatalf("first RunOnce returned error: %v", err)
	}
	if activity != 1 {
		t.Fatalf("expected first RunOnce activity 1, got %d", activity)
	}
	if consumer.InFlight() != 1 {
		t.Fatalf("expected one in-flight build after first tick, got %d", consumer.InFlight())
	}

	activity, err = consumer.RunOnce(context.Background())
	if err != nil {
		t.Fatalf("second RunOnce returned error: %v", err)
	}
	if activity != 1 {
		t.Fatalf("expected second RunOnce to submit one additional build, got %d", activity)
	}

	activity, err = consumer.RunOnce(context.Background())
	if err != nil {
		t.Fatalf("third RunOnce returned error: %v", err)
	}
	if activity < 1 {
		t.Fatalf("expected third RunOnce to collect at least one completed result, got %d", activity)
	}
	if len(queueClient.ackLeaseIDs) != 1 || queueClient.ackLeaseIDs[0] != "lease-2" {
		t.Fatalf("expected second build to ack while first is in flight, got %#v", queueClient.ackLeaseIDs)
	}
	if queueClient.pullCalls != 2 {
		t.Fatalf("expected two pull calls, got %d", queueClient.pullCalls)
	}

	close(handler.release)

	runUntilSettled(t, consumer, 4)
	if len(queueClient.ackLeaseIDs) != 2 || queueClient.ackLeaseIDs[0] != "lease-2" || queueClient.ackLeaseIDs[1] != "lease-1" {
		t.Fatalf("expected final ack for first build, got %#v", queueClient.ackLeaseIDs)
	}
}

type stubQueueClient struct {
	messages      []queue.PulledMessage
	pulls         [][]queue.PulledMessage
	ackLeaseIDs   []string
	retryLeaseIDs []string
	pullCalls     int
}

func (s *stubQueueClient) PullMessages(_ context.Context, batchSize int, _ int) ([]queue.PulledMessage, error) {
	s.pullCalls++
	if len(s.pulls) > 0 {
		messages := s.pulls[0]
		s.pulls = s.pulls[1:]
		return messages, nil
	}
	if len(s.messages) == 0 {
		return nil, nil
	}
	limit := batchSize
	if limit > len(s.messages) {
		limit = len(s.messages)
	}
	messages := append([]queue.PulledMessage(nil), s.messages[:limit]...)
	s.messages = s.messages[limit:]
	return messages, nil
}

func (s *stubQueueClient) Acknowledge(_ context.Context, acks []string, retries []string) error {
	s.ackLeaseIDs = append(s.ackLeaseIDs, acks...)
	s.retryLeaseIDs = append(s.retryLeaseIDs, retries...)
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
	return buildRequestedMessageWithBuildID(t, leaseID, attempts, "build-1")
}

func buildRequestedMessageWithBuildID(t *testing.T, leaseID string, attempts int, buildID string) queue.PulledMessage {
	t.Helper()
	payload := map[string]any{
		"schema":         "build.requested.v1",
		"build_id":       buildID,
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

type mapHandler struct {
	errs map[string]error
}

func (h *mapHandler) Handle(_ context.Context, message contracts.BuildRequestedMessage) error {
	if err, ok := h.errs[message.BuildID]; ok {
		return err
	}
	return nil
}

type blockingHandler struct {
	mu          sync.Mutex
	current     int
	maxObserved int
	started     chan string
	release     chan struct{}
}

func newBlockingHandler() *blockingHandler {
	return &blockingHandler{
		started: make(chan string, 16),
		release: make(chan struct{}),
	}
}

func (h *blockingHandler) Handle(_ context.Context, message contracts.BuildRequestedMessage) error {
	h.mu.Lock()
	h.current++
	if h.current > h.maxObserved {
		h.maxObserved = h.current
	}
	h.mu.Unlock()

	h.started <- message.BuildID
	<-h.release

	h.mu.Lock()
	h.current--
	h.mu.Unlock()
	return nil
}

type selectiveBlockingHandler struct {
	blockBuildID string
	release      chan struct{}
}

func newSelectiveBlockingHandler(blockBuildID string) *selectiveBlockingHandler {
	return &selectiveBlockingHandler{
		blockBuildID: blockBuildID,
		release:      make(chan struct{}),
	}
}

func (h *selectiveBlockingHandler) Handle(_ context.Context, message contracts.BuildRequestedMessage) error {
	if message.BuildID != h.blockBuildID {
		return nil
	}
	<-h.release
	return nil
}

func runUntilSettled(t *testing.T, consumer *Consumer, maxTicks int) {
	t.Helper()
	for i := 0; i < maxTicks; i++ {
		_, err := consumer.RunOnce(context.Background())
		if err != nil {
			t.Fatalf("RunOnce returned error: %v", err)
		}
		if consumer.InFlight() == 0 {
			_, err := consumer.RunOnce(context.Background())
			if err != nil {
				t.Fatalf("RunOnce returned error: %v", err)
			}
			if consumer.InFlight() == 0 {
				return
			}
		}
	}
	t.Fatalf("consumer did not settle within %d ticks", maxTicks)
}

func sortedCopy(values []string) []string {
	cloned := append([]string(nil), values...)
	slices.Sort(cloned)
	return cloned
}
