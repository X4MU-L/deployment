package handler

import (
	"context"

	"builder_worker/internal/artifacts"
	"builder_worker/internal/contracts"
	"builder_worker/internal/controlplane"
	"builder_worker/internal/executor"
)

type BuildHandler struct {
	controlPlaneClient ControlPlaneClient
	executor           executor.BuildExecutor
	logForwarder       BuildLogForwarder
}

type BuildHandlerConfig struct {
	ControlPlaneBaseURL   string
	ServiceToken          string
	ServiceName           string
	BuildExecutorProvider string
	CommandRunnerProvider string
	BuildDockerImage      string
	BuildDockerInstallNet string
	BuildDockerBuildNet   string
	BuildDockerPidsLimit  int
	AllowedDockerImages   []string
	ArtifactStoreProvider string
	ArtifactStoreRoot     string
	R2EndpointURL         string
	R2AccessKeyID         string
	R2SecretAccessKey     string
	R2SessionToken        string
	R2Region              string
}

// NewBuildHandler creates a new BuildHandler with the given configuration.
// It initializes the artifact publisher, build executor, and control plane client based on the provided configuration.
// The BuildHandler is responsible for handling build requests, executing builds, forwarding logs, and updating build status in the control plane.
func NewBuildHandler(config BuildHandlerConfig) (*BuildHandler, error) {
	publisher, err := artifacts.BuildPublisher(config.ArtifactStoreProvider, artifacts.PublisherConfig{
		Root:              config.ArtifactStoreRoot,
		R2EndpointURL:     config.R2EndpointURL,
		R2AccessKeyID:     config.R2AccessKeyID,
		R2SecretAccessKey: config.R2SecretAccessKey,
		R2SessionToken:    config.R2SessionToken,
		R2Region:          config.R2Region,
	})
	if err != nil {
		return nil, err
	}

	// Initialize build executor based on configuration
	// The build executor is responsible for executing the build logic, which may involve checking out source code, running build commands, and publishing artifacts.
	// We have different implementations of the build executor, such as a simulated one for testing and an actual one that runs real builds.
	buildExecutor, err := executor.Build(config.BuildExecutorProvider, executor.FactoryConfig{
		Publisher:             publisher,
		CommandRunnerProvider: config.CommandRunnerProvider,
		DockerImage:           config.BuildDockerImage,
		DockerInstallNetwork:  config.BuildDockerInstallNet,
		DockerBuildNetwork:    config.BuildDockerBuildNet,
		DockerPidsLimit:       config.BuildDockerPidsLimit,
		AllowedDockerImages:   config.AllowedDockerImages,
	})
	if err != nil {
		return nil, err
	}

	controlPlaneClient := controlplane.NewClient(
		config.ControlPlaneBaseURL,
		config.ServiceToken,
		config.ServiceName,
	)
	return &BuildHandler{
		controlPlaneClient: controlPlaneClient,
		executor:           buildExecutor,
		logForwarder:       NewControlPlaneLogForwarder(controlPlaneClient),
	}, nil
}

// NewBuildHandlerWithDeps creates a new BuildHandler with the given dependencies.
// This is useful for testing or when you want to inject specific implementations of the dependencies.
func NewBuildHandlerWithDeps(controlPlaneClient ControlPlaneClient, buildExecutor executor.BuildExecutor, logForwarder BuildLogForwarder) *BuildHandler {
	return &BuildHandler{
		controlPlaneClient: controlPlaneClient,
		executor:           buildExecutor,
		logForwarder:       logForwarder,
	}
}

func (h *BuildHandler) Handle(ctx context.Context, message contracts.BuildRequestedMessage) error {
	build, err := h.controlPlaneClient.GetBuild(ctx, message.BuildID)
	if err != nil {
		return err
	}

	if err := h.controlPlaneClient.UpdateBuildStatus(ctx, message.BuildID, controlplane.BuildStatusUpdateRequest{
		Status: "running",
	}); err != nil {
		return err
	}

	logMessages := make(chan executor.BuildLogMessage, 16)
	forwardErrCh := make(chan error, 1)
	go func() {
		forwardErrCh <- h.logForwarder.Forward(ctx, message.BuildID, logMessages)
	}()

	result, err := h.executor.Execute(ctx, executor.BuildExecutionRequest{
		Build:   build,
		Message: message,
	}, logMessages)
	close(logMessages)
	forwardErr := <-forwardErrCh
	if err != nil {
		return err
	}
	if forwardErr != nil {
		return forwardErr
	}

	return h.controlPlaneClient.CompleteBuild(ctx, message.BuildID, controlplane.BuildCompleteRequest{
		Status:       result.Status,
		ArtifactRef:  result.ArtifactRef,
		ManifestRef:  result.ManifestRef,
		ErrorMessage: result.ErrorMessage,
	})
}
