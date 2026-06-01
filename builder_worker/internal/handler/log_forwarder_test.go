package handler

import (
	"context"
	"errors"
	"testing"

	"builder_worker/internal/executor"
)

func TestControlPlaneLogForwarderStreamsLogsInOrder(t *testing.T) {
	controlPlane := &stubControlPlaneClient{}
	forwarder := NewControlPlaneLogForwarder(controlPlane)
	messages := make(chan executor.BuildLogMessage, 3)

	messages <- executor.BuildLogMessage{Stream: "stdout", Line: "line-1"}
	messages <- executor.BuildLogMessage{Stream: "stderr", Line: "line-2"}
	close(messages)

	if err := forwarder.Forward(context.Background(), "build-1", messages); err != nil {
		t.Fatalf("Forward returned error: %v", err)
	}
	if len(controlPlane.logRequests) != 2 {
		t.Fatalf("expected 2 log requests, got %d", len(controlPlane.logRequests))
	}
	if controlPlane.logRequests[0].StartSeq != 0 || controlPlane.logRequests[1].StartSeq != 1 {
		t.Fatalf("unexpected log sequences: %#v", controlPlane.logRequests)
	}
	if controlPlane.logRequests[1].Stream != "stderr" {
		t.Fatalf("unexpected second log stream: %#v", controlPlane.logRequests[1])
	}
}

func TestControlPlaneLogForwarderDrainsAfterFirstError(t *testing.T) {
	controlPlane := &stubControlPlaneClient{
		ingestErrAt: 1,
		ingestErr:   errors.New("ingest failed"),
	}
	forwarder := NewControlPlaneLogForwarder(controlPlane)
	messages := make(chan executor.BuildLogMessage, 3)

	messages <- executor.BuildLogMessage{Stream: "stdout", Line: "line-1"}
	messages <- executor.BuildLogMessage{Stream: "stdout", Line: "line-2"}
	messages <- executor.BuildLogMessage{Stream: "stdout", Line: "line-3"}
	close(messages)

	err := forwarder.Forward(context.Background(), "build-1", messages)
	if err == nil || err.Error() != "ingest failed" {
		t.Fatalf("expected ingest failed error, got %v", err)
	}
	if len(controlPlane.logRequests) != 1 {
		t.Fatalf("forwarder should stop sending after first failure, got %d requests", len(controlPlane.logRequests))
	}
}
