package handler

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"sync"
	"testing"
	"time"

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
	if len(controlPlane.logRequests) != 12 {
		t.Fatalf("expected 12 log lines, got %d", len(controlPlane.logRequests))
	}
	if controlPlane.logRequests[0].Stream != "system" || controlPlane.logRequests[1].Stream != "system" || controlPlane.logRequests[len(controlPlane.logRequests)-1].Stream != "system" {
		t.Fatalf("expected lifecycle system logs around executor logs: %#v", controlPlane.logRequests)
	}
	firstLifecycle := decodeLifecycleLog(t, controlPlane.logRequests[0].Lines[0])
	if firstLifecycle.Phase != "claim.acquired" || firstLifecycle.CorrelationID != "corr-1" || firstLifecycle.BuildID != "build-1" {
		t.Fatalf("unexpected first lifecycle log: %#v", firstLifecycle)
	}
	lastLifecycle := decodeLifecycleLog(t, controlPlane.logRequests[len(controlPlane.logRequests)-1].Lines[0])
	if lastLifecycle.Phase != "build.execution_succeeded" {
		t.Fatalf("unexpected final lifecycle log: %#v", lastLifecycle)
	}
	if controlPlane.logRequests[2].Lines[0] != "builder: received build build-1" {
		t.Fatalf("unexpected first executor log line: %#v", controlPlane.logRequests[2])
	}
	if controlPlane.logRequests[2].Stream != "stdout" {
		t.Fatalf("unexpected first executor log stream: %#v", controlPlane.logRequests[2])
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
	if controlPlane.logRequests[len(controlPlane.logRequests)-1].Stream != "system" {
		t.Fatalf("expected final lifecycle log, got %#v", controlPlane.logRequests[len(controlPlane.logRequests)-1])
	}
	lastLifecycle := decodeLifecycleLog(t, controlPlane.logRequests[len(controlPlane.logRequests)-1].Lines[0])
	if lastLifecycle.Phase != "build.execution_failed" {
		t.Fatalf("unexpected failure lifecycle log: %#v", lastLifecycle)
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

func TestBuildHandlerRenewsClaimDuringLongRunningBuild(t *testing.T) {
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
		renewResponse: controlplane.BuildClaimResponse{
			Claimed: true,
			Build: controlplane.BuildResponse{
				ID:               "build-1",
				ProjectID:        "project-1",
				PlannedReleaseID: "release-1",
				Status:           "running",
			},
		},
	}
	buildExecutor := newBlockingExecutor(executor.BuildExecutionResult{Status: "succeeded"})
	buildHandler := NewBuildHandlerWithDeps(controlPlane, buildExecutor, NewControlPlaneLogForwarder(controlPlane))
	buildHandler.claimRenewInterval = 10 * time.Millisecond

	done := make(chan error, 1)
	go func() {
		done <- buildHandler.Handle(context.Background(), buildRequestedMessage(false))
	}()

	select {
	case <-buildExecutor.started:
	case <-time.After(time.Second):
		t.Fatalf("timed out waiting for executor start")
	}

	deadline := time.After(time.Second)
	for {
		controlPlane.mu.Lock()
		renewCount := len(controlPlane.renewRequests)
		controlPlane.mu.Unlock()
		if renewCount > 0 {
			break
		}
		select {
		case <-deadline:
			t.Fatalf("timed out waiting for renew request")
		case <-time.After(10 * time.Millisecond):
		}
	}

	close(buildExecutor.release)
	if err := <-done; err != nil {
		t.Fatalf("Handle returned error: %v", err)
	}
	if len(controlPlane.completeRequests) != 1 {
		t.Fatalf("expected 1 completion request, got %d", len(controlPlane.completeRequests))
	}
}

func TestBuildHandlerReturnsRenewalErrorAndCancelsBuild(t *testing.T) {
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
		renewErr: errors.New("lease renewal failed"),
	}
	buildExecutor := &contextAwareBlockingExecutor{}
	buildHandler := NewBuildHandlerWithDeps(controlPlane, buildExecutor, NewControlPlaneLogForwarder(controlPlane))
	buildHandler.claimRenewInterval = 10 * time.Millisecond

	err := buildHandler.Handle(context.Background(), buildRequestedMessage(false))
	if err == nil || !strings.Contains(err.Error(), "lease renewal failed") {
		t.Fatalf("expected renewal error, got %v", err)
	}
	if !buildExecutor.canceled {
		t.Fatalf("expected executor context to be canceled on renewal failure")
	}
	if len(controlPlane.completeRequests) != 0 {
		t.Fatalf("completion should not be sent when renewal fails: %#v", controlPlane.completeRequests)
	}
	lastLifecycle := decodeLifecycleLog(t, controlPlane.logRequests[len(controlPlane.logRequests)-1].Lines[0])
	if lastLifecycle.Phase != "claim.renew_failed" {
		t.Fatalf("unexpected renewal failure lifecycle log: %#v", lastLifecycle)
	}
}

func TestBuildHandlerCancelsBuildWhenMaxDurationExpires(t *testing.T) {
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
	buildExecutor := &contextAwareBlockingExecutor{}
	buildHandler := NewBuildHandlerWithDeps(controlPlane, buildExecutor, NewControlPlaneLogForwarder(controlPlane))
	buildHandler.claimRenewInterval = time.Hour
	buildHandler.buildMaxDuration = 20 * time.Millisecond

	err := buildHandler.Handle(context.Background(), buildRequestedMessage(false))
	if err == nil || !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("expected deadline exceeded error, got %v", err)
	}
	if !buildExecutor.canceled {
		t.Fatalf("expected executor context to be canceled on build timeout")
	}
	if len(controlPlane.completeRequests) != 0 {
		t.Fatalf("completion should not be sent when build times out: %#v", controlPlane.completeRequests)
	}
	lastLifecycle := decodeLifecycleLog(t, controlPlane.logRequests[len(controlPlane.logRequests)-1].Lines[0])
	if lastLifecycle.Phase != "build.execution_timed_out" {
		t.Fatalf("unexpected timeout lifecycle log: %#v", lastLifecycle)
	}
}

type stubControlPlaneClient struct {
	build            controlplane.BuildResponse
	claimResponse    controlplane.BuildClaimResponse
	renewResponse    controlplane.BuildClaimResponse
	claimRequests    []controlplane.BuildClaimRequest
	renewRequests    []controlplane.BuildClaimRequest
	statusUpdates    []controlplane.BuildStatusUpdateRequest
	logRequests      []controlplane.BuildLogIngestRequest
	completeRequests []controlplane.BuildCompleteRequest
	ingestErrAt      int
	ingestErr        error
	renewErr         error
	mu               sync.Mutex
}

func (s *stubControlPlaneClient) GetBuild(_ context.Context, _ string) (controlplane.BuildResponse, error) {
	return s.build, nil
}

func (s *stubControlPlaneClient) ClaimBuild(_ context.Context, _ string, request controlplane.BuildClaimRequest) (controlplane.BuildClaimResponse, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.claimRequests = append(s.claimRequests, request)
	return s.claimResponse, nil
}

func (s *stubControlPlaneClient) RenewBuildClaim(_ context.Context, _ string, request controlplane.BuildClaimRequest) (controlplane.BuildClaimResponse, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.renewRequests = append(s.renewRequests, request)
	if s.renewErr != nil {
		return controlplane.BuildClaimResponse{}, s.renewErr
	}
	return s.renewResponse, nil
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

type blockingExecutor struct {
	result  executor.BuildExecutionResult
	started chan struct{}
	release chan struct{}
}

func newBlockingExecutor(result executor.BuildExecutionResult) *blockingExecutor {
	return &blockingExecutor{
		result:  result,
		started: make(chan struct{}, 1),
		release: make(chan struct{}),
	}
}

func (b *blockingExecutor) Execute(ctx context.Context, _ executor.BuildExecutionRequest, _ chan<- executor.BuildLogMessage) (executor.BuildExecutionResult, error) {
	select {
	case b.started <- struct{}{}:
	default:
	}
	select {
	case <-ctx.Done():
		return executor.BuildExecutionResult{}, ctx.Err()
	case <-b.release:
		return b.result, nil
	}
}

type contextAwareBlockingExecutor struct {
	canceled bool
}

func (e *contextAwareBlockingExecutor) Execute(ctx context.Context, _ executor.BuildExecutionRequest, _ chan<- executor.BuildLogMessage) (executor.BuildExecutionResult, error) {
	<-ctx.Done()
	e.canceled = true
	return executor.BuildExecutionResult{}, ctx.Err()
}

type stubLogForwarder struct {
	err error
}

func (s *stubLogForwarder) Forward(_ context.Context, _ string, messages <-chan executor.BuildLogMessage) error {
	for range messages {
	}
	return s.err
}

func decodeLifecycleLog(t *testing.T, content string) lifecycleLogEntry {
	t.Helper()
	var entry lifecycleLogEntry
	if err := json.Unmarshal([]byte(content), &entry); err != nil {
		t.Fatalf("decode lifecycle log: %v", err)
	}
	return entry
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
