package handler

import (
	"context"

	"builder_worker/internal/controlplane"
	"builder_worker/internal/executor"
	"builder_worker/internal/logger"
)

type BuildLogForwarder interface {
	Forward(context.Context, string, <-chan executor.BuildLogMessage) error
}

type ControlPlaneLogForwarder struct {
	controlPlaneClient ControlPlaneClient
}

func NewControlPlaneLogForwarder(controlPlaneClient ControlPlaneClient) *ControlPlaneLogForwarder {
	return &ControlPlaneLogForwarder{controlPlaneClient: controlPlaneClient}
}

func (f *ControlPlaneLogForwarder) Forward(ctx context.Context, buildID string, messages <-chan executor.BuildLogMessage) error {
	seq := 0
	var firstErr error

	for message := range messages {
		logForwardedMessage(buildID, message)
		if firstErr != nil {
			continue
		}
		err := f.controlPlaneClient.IngestBuildLogs(ctx, buildID, controlplane.BuildLogIngestRequest{
			Stream:   message.Stream,
			Lines:    []string{message.Line},
			StartSeq: seq,
		})
		seq += 1
		if err != nil {
			firstErr = err
		}
	}

	return firstErr
}

func logForwardedMessage(buildID string, message executor.BuildLogMessage) {
	switch message.Stream {
	case "stderr":
		logger.Warn("build stream", "build_id", buildID, "stream", message.Stream, "line", logger.Literal(message.Line))
	case "system":
		logger.Info("build stream", "build_id", buildID, "stream", message.Stream, "line", logger.Literal(message.Line))
	default:
		logger.Info("build stream", "build_id", buildID, "stream", message.Stream, "line", logger.Literal(message.Line))
	}
}
