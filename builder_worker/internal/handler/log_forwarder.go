package handler

import (
	"context"

	"builder_worker/internal/controlplane"
	"builder_worker/internal/executor"
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
