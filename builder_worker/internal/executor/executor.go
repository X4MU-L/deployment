package executor

import (
	"context"

	"builder_worker/internal/contracts"
	"builder_worker/internal/controlplane"
)

type BuildExecutor interface {
	Execute(context.Context, BuildExecutionRequest, chan<- BuildLogMessage) (BuildExecutionResult, error)
}

type BuildExecutionRequest struct {
	Build   controlplane.BuildResponse
	Message contracts.BuildRequestedMessage
}

type BuildLogMessage struct {
	Stream string
	Line   string
}

type BuildExecutionResult struct {
	Status       string
	ArtifactRef  string
	ManifestRef  string
	ErrorMessage string
}
