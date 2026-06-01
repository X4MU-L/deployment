package handler

import (
	"context"

	"builder_worker/internal/controlplane"
)

type ControlPlaneClient interface {
	GetBuild(context.Context, string) (controlplane.BuildResponse, error)
	UpdateBuildStatus(context.Context, string, controlplane.BuildStatusUpdateRequest) error
	IngestBuildLogs(context.Context, string, controlplane.BuildLogIngestRequest) error
	CompleteBuild(context.Context, string, controlplane.BuildCompleteRequest) error
}
