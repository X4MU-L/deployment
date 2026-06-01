package handler

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"builder_worker/internal/artifacts"
	"builder_worker/internal/contracts"
	"builder_worker/internal/controlplane"
	"builder_worker/internal/executor"
	"builder_worker/internal/logger"
)

const defaultBuildClaimLeaseSeconds = 900
const defaultBuildClaimRenewInterval = 5 * time.Minute
const defaultBuildMaxDuration = 14 * time.Minute

type BuildHandler struct {
	controlPlaneClient ControlPlaneClient
	executor           executor.BuildExecutor
	logForwarder       BuildLogForwarder
	serviceName        string
	claimLeaseSeconds  int
	claimRenewInterval time.Duration
	buildMaxDuration   time.Duration
}

type BuildHandlerConfig struct {
	ControlPlaneBaseURL   string
	ServiceToken          string
	ServiceName           string
	ClaimLeaseSeconds     int
	ClaimRenewInterval    time.Duration
	BuildMaxDuration      time.Duration
	BuildExecutorProvider string
	SourceFetcherProvider string
	FetchDockerImage      string
	FetchDockerNetwork    string
	FetchDockerCPUs       string
	FetchDockerMemory     string
	FetchDockerMemorySwap string
	FetchDockerPidsLimit  int
	CommandRunnerProvider string
	BuildDockerImage      string
	BuildDockerInstallNet string
	BuildDockerBuildNet   string
	BuildDockerCPUs       string
	BuildDockerMemory     string
	BuildDockerMemorySwap string
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
		SourceFetcherProvider: config.SourceFetcherProvider,
		FetchDockerImage:      config.FetchDockerImage,
		FetchDockerNetwork:    config.FetchDockerNetwork,
		FetchDockerCPUs:       config.FetchDockerCPUs,
		FetchDockerMemory:     config.FetchDockerMemory,
		FetchDockerMemorySwap: config.FetchDockerMemorySwap,
		FetchDockerPidsLimit:  config.FetchDockerPidsLimit,
		CommandRunnerProvider: config.CommandRunnerProvider,
		DockerImage:           config.BuildDockerImage,
		DockerInstallNetwork:  config.BuildDockerInstallNet,
		DockerBuildNetwork:    config.BuildDockerBuildNet,
		DockerCPUs:            config.BuildDockerCPUs,
		DockerMemory:          config.BuildDockerMemory,
		DockerMemorySwap:      config.BuildDockerMemorySwap,
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
		serviceName:        config.ServiceName,
		claimLeaseSeconds:  coalesceClaimLeaseSeconds(config.ClaimLeaseSeconds),
		claimRenewInterval: coalesceClaimRenewInterval(config.ClaimRenewInterval),
		buildMaxDuration:   coalesceBuildMaxDuration(config.BuildMaxDuration),
	}, nil
}

// NewBuildHandlerWithDeps creates a new BuildHandler with the given dependencies.
// This is useful for testing or when you want to inject specific implementations of the dependencies.
func NewBuildHandlerWithDeps(controlPlaneClient ControlPlaneClient, buildExecutor executor.BuildExecutor, logForwarder BuildLogForwarder) *BuildHandler {
	return &BuildHandler{
		controlPlaneClient: controlPlaneClient,
		executor:           buildExecutor,
		logForwarder:       logForwarder,
		serviceName:        "builder-worker",
		claimLeaseSeconds:  defaultBuildClaimLeaseSeconds,
		claimRenewInterval: defaultBuildClaimRenewInterval,
		buildMaxDuration:   defaultBuildMaxDuration,
	}
}

func (h *BuildHandler) Handle(ctx context.Context, message contracts.BuildRequestedMessage) error {
	logger.Info(
		"build handler started",
		"build_id",
		message.BuildID,
		"project_id",
		message.ProjectID,
		"environment_id",
		message.EnvironmentID,
		"release_id",
		message.ReleaseID,
		"correlation_id",
		message.CorrelationID,
		"attempt",
		message.Attempt,
	)
	claim, err := h.controlPlaneClient.ClaimBuild(ctx, message.BuildID, controlplane.BuildClaimRequest{
		LeaseSeconds: h.claimLeaseSeconds,
	})
	if err != nil {
		logger.Error("build handler claim request failed", "build_id", message.BuildID, "correlation_id", message.CorrelationID, "err", err)
		return err
	}
	if !claim.Claimed {
		reason := claim.Reason
		if reason == "" {
			reason = "not_claimable"
		}
		logger.Warn("build handler claim denied", "build_id", message.BuildID, "correlation_id", message.CorrelationID, "reason", reason)
		return TerminalError(fmt.Errorf("build claim denied for %s: %s", message.BuildID, reason))
	}
	build := claim.Build
	logger.Info(
		"build handler claim acquired",
		"build_id",
		message.BuildID,
		"status",
		build.Status,
		"project_id",
		build.ProjectID,
		"lease_seconds",
		h.claimLeaseSeconds,
	)

	logCtx, stopLogs := context.WithCancel(ctx)
	defer stopLogs()

	logMessages := make(chan executor.BuildLogMessage, 16)
	forwardErrCh := make(chan error, 1)
	go func() {
		forwardErrCh <- h.logForwarder.Forward(logCtx, message.BuildID, logMessages)
	}()

	if err := h.emitLifecycleLog(logCtx, logMessages, message, "claim.acquired", map[string]any{
		"lease_seconds": h.claimLeaseSeconds,
	}); err != nil {
		logger.Error("build handler lifecycle log failed", "build_id", message.BuildID, "phase", "claim.acquired", "err", err)
		close(logMessages)
		<-forwardErrCh
		return err
	}
	if err := h.emitLifecycleLog(logCtx, logMessages, message, "build.started", map[string]any{
		"build_max_duration_seconds": int(h.buildMaxDuration / time.Second),
	}); err != nil {
		logger.Error("build handler lifecycle log failed", "build_id", message.BuildID, "phase", "build.started", "err", err)
		close(logMessages)
		<-forwardErrCh
		return err
	}

	execCtx, cancel := context.WithTimeout(ctx, h.buildMaxDuration)
	defer cancel()
	logger.Info("build handler executor starting", "build_id", message.BuildID, "correlation_id", message.CorrelationID, "max_duration", h.buildMaxDuration)

	renewErrCh := make(chan error, 1)
	go func() {
		renewErrCh <- h.renewClaimLoop(execCtx, message, logMessages, cancel)
	}()

	result, executeErr := h.executor.Execute(execCtx, executor.BuildExecutionRequest{
		Build:   build,
		Message: message,
	}, logMessages)
	logger.Info(
		"build handler executor finished",
		"build_id",
		message.BuildID,
		"correlation_id",
		message.CorrelationID,
		"status",
		result.Status,
		"ErrorMessage",
		result.ErrorMessage,
		"artifact_ref",
		result.ArtifactRef,
		"manifest_ref",
		result.ManifestRef,
		"execute_err",
		executeErr,
	)
	cancel()
	renewErr := <-renewErrCh

	var lifecycleErr error
	if executeErr == nil && renewErr == nil {
		lifecycleErr = h.emitLifecycleLog(logCtx, logMessages, message, classifyResultPhase(result.Status), map[string]any{
			"status":       result.Status,
			"artifact_ref": result.ArtifactRef,
			"manifest_ref": result.ManifestRef,
			"error":        result.ErrorMessage,
		})
	} else {
		lifecycleErr = h.emitLifecycleLog(logCtx, logMessages, message, classifyFailurePhase(executeErr, renewErr), map[string]any{
			"error": firstErrorString(prioritizeRenewalError(executeErr, renewErr)),
		})
	}
	close(logMessages)
	forwardErr := <-forwardErrCh
	stopLogs()
	logger.Info(
		"build handler log forwarding finished",
		"build_id",
		message.BuildID,
		"correlation_id",
		message.CorrelationID,
		"execute_err",
		executeErr,
		"renew_err",
		renewErr,
		"forward_err",
		forwardErr,
	)

	if err := joinNonNil(
		prioritizeRenewalError(executeErr, renewErr),
		lifecycleErr,
		forwardErr,
	); err != nil {
		logger.Error("build handler failed", "build_id", message.BuildID, "correlation_id", message.CorrelationID, "err", err)
		return err
	}

	logger.Info(
		"build handler reporting completion",
		"build_id",
		message.BuildID,
		"correlation_id",
		message.CorrelationID,
		"status",
		result.Status,
		"artifact_ref",
		result.ArtifactRef,
		"manifest_ref",
		result.ManifestRef,
	)
	if err := h.controlPlaneClient.CompleteBuild(ctx, message.BuildID, controlplane.BuildCompleteRequest{
		Status:       result.Status,
		ArtifactRef:  result.ArtifactRef,
		ManifestRef:  result.ManifestRef,
		ErrorMessage: result.ErrorMessage,
	}); err != nil {
		logger.Error("build handler completion callback failed", "build_id", message.BuildID, "correlation_id", message.CorrelationID, "err", err)
		return err
	}

	logger.Info("build handler completed", "build_id", message.BuildID, "correlation_id", message.CorrelationID, "status", result.Status)
	return nil
}

func (h *BuildHandler) renewClaimLoop(
	ctx context.Context,
	message contracts.BuildRequestedMessage,
	logSink chan<- executor.BuildLogMessage,
	cancel context.CancelFunc,
) error {
	ticker := time.NewTicker(h.claimRenewInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
			response, err := h.controlPlaneClient.RenewBuildClaim(ctx, message.BuildID, controlplane.BuildClaimRequest{
				LeaseSeconds: h.claimLeaseSeconds,
			})
			if err != nil {
				cancel()
				logger.Error("build handler claim renewal failed", "build_id", message.BuildID, "correlation_id", message.CorrelationID, "err", err)
				return fmt.Errorf("renew build claim: %w", err)
			}
			if !response.Claimed {
				cancel()
				reason := response.Reason
				if reason == "" {
					reason = "not_claimable"
				}
				logger.Warn("build handler claim renewal denied", "build_id", message.BuildID, "correlation_id", message.CorrelationID, "reason", reason)
				return fmt.Errorf("renew build claim denied for %s: %s", message.BuildID, reason)
			}
			logger.Debug("build handler claim renewed", "build_id", message.BuildID, "correlation_id", message.CorrelationID, "lease_seconds", h.claimLeaseSeconds)
			if err := h.emitLifecycleLog(ctx, logSink, message, "claim.renewed", map[string]any{
				"lease_seconds": h.claimLeaseSeconds,
			}); err != nil {
				cancel()
				return err
			}
		}
	}
}

type lifecycleLogEntry struct {
	Kind          string         `json:"kind"`
	Phase         string         `json:"phase"`
	BuildID       string         `json:"build_id"`
	ProjectID     string         `json:"project_id"`
	EnvironmentID string         `json:"environment_id"`
	ReleaseID     string         `json:"release_id"`
	CorrelationID string         `json:"correlation_id"`
	Attempt       int            `json:"attempt"`
	Service       string         `json:"service"`
	Fields        map[string]any `json:"fields,omitempty"`
}

func (h *BuildHandler) emitLifecycleLog(
	ctx context.Context,
	logSink chan<- executor.BuildLogMessage,
	message contracts.BuildRequestedMessage,
	phase string,
	fields map[string]any,
) error {
	entry := lifecycleLogEntry{
		Kind:          "lifecycle",
		Phase:         phase,
		BuildID:       message.BuildID,
		ProjectID:     message.ProjectID,
		EnvironmentID: message.EnvironmentID,
		ReleaseID:     message.ReleaseID,
		CorrelationID: message.CorrelationID,
		Attempt:       message.Attempt,
		Service:       h.serviceName,
		Fields:        fields,
	}
	encoded, err := json.Marshal(entry)
	if err != nil {
		return fmt.Errorf("marshal lifecycle log: %w", err)
	}
	select {
	case <-ctx.Done():
		return ctx.Err()
	case logSink <- executor.BuildLogMessage{Stream: "system", Line: string(encoded)}:
		return nil
	}
}

func coalesceClaimLeaseSeconds(value int) int {
	if value < 1 {
		return defaultBuildClaimLeaseSeconds
	}
	return value
}

func coalesceClaimRenewInterval(value time.Duration) time.Duration {
	if value <= 0 {
		return defaultBuildClaimRenewInterval
	}
	return value
}

func coalesceBuildMaxDuration(value time.Duration) time.Duration {
	if value <= 0 {
		return defaultBuildMaxDuration
	}
	return value
}

func prioritizeRenewalError(executeErr error, renewErr error) error {
	if renewErr == nil {
		return executeErr
	}
	if executeErr == nil || errors.Is(executeErr, context.Canceled) {
		return renewErr
	}
	return errors.Join(executeErr, renewErr)
}

func joinNonNil(errs ...error) error {
	filtered := make([]error, 0, len(errs))
	for _, err := range errs {
		if err != nil {
			filtered = append(filtered, err)
		}
	}
	if len(filtered) == 0 {
		return nil
	}
	return errors.Join(filtered...)
}

func classifyFailurePhase(executeErr error, renewErr error) string {
	if renewErr != nil {
		return "claim.renew_failed"
	}
	if errors.Is(executeErr, context.DeadlineExceeded) {
		return "build.execution_timed_out"
	}
	if errors.Is(executeErr, context.Canceled) {
		return "build.execution_canceled"
	}
	return "build.execution_failed"
}

func classifyResultPhase(status string) string {
	switch status {
	case "succeeded":
		return "build.execution_succeeded"
	case "failed":
		return "build.execution_failed"
	case "canceled":
		return "build.execution_canceled"
	default:
		return "build.execution_finished"
	}
}

func firstErrorString(err error) string {
	if err == nil {
		return ""
	}
	return err.Error()
}
