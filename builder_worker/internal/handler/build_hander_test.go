package handler

import (
	"context"
	"errors"
	"strings"
	"testing"

	"builder_worker/internal/consumer"
	"builder_worker/internal/contracts"
	"builder_worker/internal/controlplane"
	"builder_worker/internal/executor"
)

func TestBuildHandlerCompletesSuccessfulBuild(t *testing.T) {
	controlPlane := &stubControlPlaneClient{
		claimResponse: controlplane.BuildClaimResponse{
			Claimed: true,
			Build: controlplane.BuildResponse{
				ID:               "build-1",
				ProjectID:        "project-1",
				PlannedReleaseID: "release-1",
				SourceRef:        "refs/heads/main",
				SourceSnapshot: map[string]any{
					"project_name": "demo-app",
				},
				BuildConfig: map[string]any{
					"output_directory": "dist",
				},
			},
		},
	}
	buildExecutor := &stubExecutor{
		result: executor.BuildExecutionResult{
			Status:      "succeeded",
			ArtifactRef: "r2://static-artifacts/projects/project-1/releases/release-1",
			ManifestRef: "r2://static-artifacts/projects/project-1/releases/release-1/static_release_manifest.v1.json",
		},
		logs: []executor.BuildLogMessage{
			{Stream: "stdout", Line: "builder: received build build-1"},
			{Stream: "stdout", Line: "source: https://github.com/example/demo"},
			{Stream: "stdout", Line: "checkout ref: refs/heads/main"},
			{Stream: "stdout", Line: "repo visibility: assumed public"},
			{Stream: "stdout", Line: "install: simulated dependency install completed"},
			{Stream: "stdout", Line: "build: simulated static site build completed"},
			{Stream: "stdout", Line: "output: simulated static files generated in dist"},
			{Stream: "stdout", Line: "upload: published simulated static release to r2://static-artifacts/projects/project-1/releases/release-1"},
			{Stream: "stdout", Line: "upload: generated static_release_manifest.v1"},
		},
	}
	buildHandler := NewBuildHandlerWithDeps(controlPlane, buildExecutor, NewControlPlaneLogForwarder(controlPlane))

	err := buildHandler.Handle(context.Background(), buildRequestedMessage(false))
	if err != nil {
		t.Fatalf("Handle returned error: %v", err)
	}

	if len(controlPlane.claimRequests) != 1 || controlPlane.claimRequests[0].LeaseSeconds != defaultBuildClaimLeaseSeconds {
		t.Fatalf("unexpected claim requests: %#v", controlPlane.claimRequests)
	}
	if len(controlPlane.statusUpdates) != 0 {
		t.Fatalf("did not expect direct status updates when claim endpoint is used: %#v", controlPlane.statusUpdates)
	}
	if len(controlPlane.logRequests) != 9 {
		t.Fatalf("expected 9 log lines, got %d", len(controlPlane.logRequests))
	}
	if controlPlane.logRequests[0].Lines[0] != "builder: received build build-1" {
		t.Fatalf("unexpected first log line: %#v", controlPlane.logRequests[0])
	}
	if controlPlane.logRequests[0].Stream != "stdout" {
		t.Fatalf("unexpected first log stream: %#v", controlPlane.logRequests[0])
	}
	if len(controlPlane.completeRequests) != 1 {
		t.Fatalf("expected 1 completion request, got %d", len(controlPlane.completeRequests))
	}
	completion := controlPlane.completeRequests[0]
	if completion.Status != "succeeded" {
		t.Fatalf("unexpected completion status: %#v", completion)
	}
	if completion.ArtifactRef != buildExecutor.result.ArtifactRef || completion.ManifestRef != buildExecutor.result.ManifestRef {
		t.Fatalf("unexpected completion refs: %#v", completion)
	}
	if len(buildExecutor.requests) != 1 {
		t.Fatalf("expected executor to be called once, got %d", len(buildExecutor.requests))
	}
}

func TestBuildHandlerFailsUnsupportedRepo(t *testing.T) {
	controlPlane := &stubControlPlaneClient{
		claimResponse: controlplane.BuildClaimResponse{
			Claimed: true,
			Build: controlplane.BuildResponse{
				ID:               "build-1",
				ProjectID:        "project-1",
				PlannedReleaseID: "release-1",
				SourceRef:        "refs/heads/main",
			},
		},
	}
	buildExecutor := &stubExecutor{
		result: executor.BuildExecutionResult{
			Status:       "failed",
			ErrorMessage: "simulated builder currently supports only public https://github.com repos",
		},
		logs: []executor.BuildLogMessage{
			{Stream: "stdout", Line: "builder: received build build-1"},
			{Stream: "stdout", Line: "source: git@github.com:example/demo.git"},
			{Stream: "stdout", Line: "checkout ref: refs/heads/main"},
			{Stream: "stdout", Line: "repo visibility: unsupported for simulated builder"},
			{Stream: "stderr", Line: "error: simulated builder currently supports only public https://github.com repos"},
		},
	}
	buildHandler := NewBuildHandlerWithDeps(controlPlane, buildExecutor, NewControlPlaneLogForwarder(controlPlane))

	message := buildRequestedMessage(false)
	message.GitCheckout.RepoURL = "git@github.com:example/demo.git"

	err := buildHandler.Handle(context.Background(), message)
	if err != nil {
		t.Fatalf("Handle returned error: %v", err)
	}

	if len(controlPlane.completeRequests) != 1 || controlPlane.completeRequests[0].Status != "failed" {
		t.Fatalf("unexpected completion requests: %#v", controlPlane.completeRequests)
	}
	if !strings.Contains(controlPlane.completeRequests[0].ErrorMessage, "https://github.com") {
		t.Fatalf("unexpected error message: %#v", controlPlane.completeRequests[0])
	}
	if controlPlane.logRequests[len(controlPlane.logRequests)-1].Stream != "stderr" {
		t.Fatalf("expected stderr log stream for error line, got %#v", controlPlane.logRequests[len(controlPlane.logRequests)-1])
	}
}

func TestBuildHandlerFailsWhenExecutorReturnsError(t *testing.T) {
	controlPlane := &stubControlPlaneClient{
		claimResponse: controlplane.BuildClaimResponse{
			Claimed: true,
			Build: controlplane.BuildResponse{
				ID:               "build-1",
				ProjectID:        "project-1",
				PlannedReleaseID: "release-1",
				SourceRef:        "refs/heads/main",
			},
		},
	}
	buildExecutor := &stubExecutor{
		err:  errors.New("r2 upload failed"),
		logs: []executor.BuildLogMessage{{Stream: "stdout", Line: "builder: received build build-1"}},
	}
	buildHandler := NewBuildHandlerWithDeps(controlPlane, buildExecutor, NewControlPlaneLogForwarder(controlPlane))

	err := buildHandler.Handle(context.Background(), buildRequestedMessage(false))
	if err == nil || !strings.Contains(err.Error(), "r2 upload failed") {
		t.Fatalf("expected executor error to bubble up, got %v", err)
	}
	if len(controlPlane.completeRequests) != 0 {
		t.Fatalf("completion should not be sent when executor returns error: %#v", controlPlane.completeRequests)
	}
}

func TestBuildHandlerUsesRepositoryPrivacyMetadata(t *testing.T) {
	controlPlane := &stubControlPlaneClient{
		claimResponse: controlplane.BuildClaimResponse{
			Claimed: true,
			Build: controlplane.BuildResponse{
				ID:               "build-1",
				ProjectID:        "project-1",
				PlannedReleaseID: "release-1",
				SourceSnapshot: map[string]any{
					"source_repository": map[string]any{"private": true},
				},
			},
		},
	}
	buildExecutor := &stubExecutor{
		result: executor.BuildExecutionResult{
			Status:       "failed",
			ErrorMessage: "private repositories are not supported in the simulated builder flow",
		},
		logs: []executor.BuildLogMessage{
			{Stream: "stdout", Line: "builder: received build build-1"},
			{Stream: "stdout", Line: "source: https://github.com/example/demo"},
			{Stream: "stdout", Line: "checkout ref: refs/heads/main"},
			{Stream: "stdout", Line: "repo visibility: unsupported for simulated builder"},
			{Stream: "stderr", Line: "error: private repositories are not supported in the simulated builder flow"},
		},
	}
	buildHandler := NewBuildHandlerWithDeps(controlPlane, buildExecutor, NewControlPlaneLogForwarder(controlPlane))

	message := buildRequestedMessage(true)
	err := buildHandler.Handle(context.Background(), message)
	if err != nil {
		t.Fatalf("Handle returned error: %v", err)
	}
	if len(controlPlane.completeRequests) != 1 || controlPlane.completeRequests[0].Status != "failed" {
		t.Fatalf("unexpected completion requests: %#v", controlPlane.completeRequests)
	}
	if !strings.Contains(controlPlane.completeRequests[0].ErrorMessage, "private repositories") {
		t.Fatalf("unexpected error message: %#v", controlPlane.completeRequests[0])
	}
}

func TestBuildHandlerReturnsLogForwarderError(t *testing.T) {
	controlPlane := &stubControlPlaneClient{
		claimResponse: controlplane.BuildClaimResponse{
			Claimed: true,
			Build: controlplane.BuildResponse{
				ID:               "build-1",
				ProjectID:        "project-1",
				PlannedReleaseID: "release-1",
			},
		},
	}
	buildExecutor := &stubExecutor{
		result: executor.BuildExecutionResult{Status: "succeeded"},
		logs: []executor.BuildLogMessage{
			{Stream: "stdout", Line: "builder: received build build-1"},
			{Stream: "stdout", Line: "source: https://github.com/example/demo"},
		},
	}
	buildHandler := NewBuildHandlerWithDeps(controlPlane, buildExecutor, &stubLogForwarder{err: errors.New("log forwarding failed")})

	err := buildHandler.Handle(context.Background(), buildRequestedMessage(false))
	if err == nil || !strings.Contains(err.Error(), "log forwarding failed") {
		t.Fatalf("expected log forwarding error, got %v", err)
	}
	if len(controlPlane.completeRequests) != 0 {
		t.Fatalf("completion should not be sent when log forwarding fails: %#v", controlPlane.completeRequests)
	}
}

func TestBuildHandlerReturnsTerminalErrorWhenClaimDenied(t *testing.T) {
	controlPlane := &stubControlPlaneClient{
		claimResponse: controlplane.BuildClaimResponse{
			Claimed: false,
			Reason:  "lease_active",
			Build: controlplane.BuildResponse{
				ID:               "build-1",
				ProjectID:        "project-1",
				PlannedReleaseID: "release-1",
				Status:           "running",
			},
		},
	}
	buildExecutor := &stubExecutor{}
	buildHandler := NewBuildHandlerWithDeps(controlPlane, buildExecutor, NewControlPlaneLogForwarder(controlPlane))

	err := buildHandler.Handle(context.Background(), buildRequestedMessage(false))
	if err == nil || !consumer.IsTerminalError(err) {
		t.Fatalf("expected terminal claim-denied error, got %v", err)
	}
	if len(buildExecutor.requests) != 0 {
		t.Fatalf("executor should not run when claim is denied: %#v", buildExecutor.requests)
	}
	if len(controlPlane.completeRequests) != 0 {
		t.Fatalf("completion should not be sent when claim is denied: %#v", controlPlane.completeRequests)
	}
}

type stubControlPlaneClient struct {
	build            controlplane.BuildResponse
	claimResponse    controlplane.BuildClaimResponse
	claimRequests    []controlplane.BuildClaimRequest
	statusUpdates    []controlplane.BuildStatusUpdateRequest
	logRequests      []controlplane.BuildLogIngestRequest
	completeRequests []controlplane.BuildCompleteRequest
	ingestErrAt      int
	ingestErr        error
}

func (s *stubControlPlaneClient) GetBuild(_ context.Context, _ string) (controlplane.BuildResponse, error) {
	return s.build, nil
}

func (s *stubControlPlaneClient) ClaimBuild(_ context.Context, _ string, request controlplane.BuildClaimRequest) (controlplane.BuildClaimResponse, error) {
	s.claimRequests = append(s.claimRequests, request)
	return s.claimResponse, nil
}

func (s *stubControlPlaneClient) UpdateBuildStatus(_ context.Context, _ string, request controlplane.BuildStatusUpdateRequest) error {
	s.statusUpdates = append(s.statusUpdates, request)
	return nil
}

func (s *stubControlPlaneClient) IngestBuildLogs(_ context.Context, _ string, request controlplane.BuildLogIngestRequest) error {
	s.logRequests = append(s.logRequests, request)
	if s.ingestErr != nil && len(s.logRequests) == s.ingestErrAt {
		return s.ingestErr
	}
	return nil
}

func (s *stubControlPlaneClient) CompleteBuild(_ context.Context, _ string, request controlplane.BuildCompleteRequest) error {
	s.completeRequests = append(s.completeRequests, request)
	return nil
}

type stubExecutor struct {
	result   executor.BuildExecutionResult
	err      error
	logs     []executor.BuildLogMessage
	requests []executor.BuildExecutionRequest
}

func (s *stubExecutor) Execute(_ context.Context, request executor.BuildExecutionRequest, logSink chan<- executor.BuildLogMessage) (executor.BuildExecutionResult, error) {
	s.requests = append(s.requests, request)
	for _, message := range s.logs {
		logSink <- message
	}
	if s.err != nil {
		return executor.BuildExecutionResult{}, s.err
	}
	return s.result, nil
}

type stubLogForwarder struct {
	err error
}

func (s *stubLogForwarder) Forward(_ context.Context, _ string, messages <-chan executor.BuildLogMessage) error {
	for range messages {
	}
	return s.err
}

func buildRequestedMessage(private bool) contracts.BuildRequestedMessage {
	return contracts.BuildRequestedMessage{
		SchemaName:    contracts.BuildRequestedSchema,
		BuildID:       "build-1",
		ProjectID:     "project-1",
		EnvironmentID: "env-1",
		ReleaseID:     "release-1",
		CorrelationID: "corr-1",
		Attempt:       1,
		GitCheckout: contracts.GitCheckoutMetadata{
			RepoURL:       "https://github.com/example/demo",
			DefaultBranch: "main",
			SourceRef:     "refs/heads/main",
			Repository: map[string]any{
				"full_name": "example/demo",
				"private":   private,
			},
		},
		BuildSpec: contracts.StaticBuildSpec{
			Kind:            "static",
			OutputDirectory: "dist",
		},
		ArtifactTarget: contracts.ArtifactTarget{
			Provider:    "r2",
			Bucket:      "static-artifacts",
			Prefix:      "projects/project-1/releases/release-1",
			ManifestKey: "projects/project-1/releases/release-1/static_release_manifest.v1.json",
		},
	}
}
