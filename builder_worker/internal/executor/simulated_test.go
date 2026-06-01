package executor

import (
	"context"
	"errors"
	"strings"
	"testing"

	"builder_worker/internal/artifacts"
	"builder_worker/internal/contracts"
	"builder_worker/internal/controlplane"
)

func TestSimulatedBuildExecutorSuccess(t *testing.T) {
	publisher := &stubPublisher{
		result: artifacts.PublishResult{
			ArtifactRef: "r2://static-artifacts/projects/project-1/releases/release-1",
			ManifestRef: "r2://static-artifacts/projects/project-1/releases/release-1/static_release_manifest.v1.json",
		},
	}
	exec := NewSimulatedBuildExecutor(publisher)
	logs := make(chan BuildLogMessage, 16)

	result, err := exec.Execute(context.Background(), BuildExecutionRequest{
		Build:   buildResponse(),
		Message: buildRequestedMessage(false),
	}, logs)
	if err != nil {
		t.Fatalf("Execute returned error: %v", err)
	}
	emitted := drainLogMessages(logs)
	if result.Status != "succeeded" {
		t.Fatalf("unexpected status: %#v", result)
	}
	if len(emitted) != 9 {
		t.Fatalf("expected 9 log lines, got %d", len(emitted))
	}
	if !strings.Contains(result.ArtifactRef, "r2://static-artifacts/") {
		t.Fatalf("unexpected artifact ref: %s", result.ArtifactRef)
	}
	if len(publisher.inputs) != 1 {
		t.Fatalf("expected publisher call, got %d", len(publisher.inputs))
	}
}

func TestSimulatedBuildExecutorUnsupportedRepo(t *testing.T) {
	exec := NewSimulatedBuildExecutor(&stubPublisher{})
	message := buildRequestedMessage(false)
	message.GitCheckout.RepoURL = "git@github.com:example/demo.git"
	logs := make(chan BuildLogMessage, 16)

	result, err := exec.Execute(context.Background(), BuildExecutionRequest{
		Build:   buildResponse(),
		Message: message,
	}, logs)
	if err != nil {
		t.Fatalf("Execute returned error: %v", err)
	}
	emitted := drainLogMessages(logs)
	if result.Status != "failed" {
		t.Fatalf("unexpected status: %#v", result)
	}
	if !strings.Contains(result.ErrorMessage, "https://github.com") {
		t.Fatalf("unexpected error message: %s", result.ErrorMessage)
	}
	if len(emitted) != 5 {
		t.Fatalf("expected 5 log lines, got %d", len(emitted))
	}
}

func TestSimulatedBuildExecutorPublisherFailure(t *testing.T) {
	exec := NewSimulatedBuildExecutor(&stubPublisher{err: errors.New("upload failed")})
	logs := make(chan BuildLogMessage, 16)

	result, err := exec.Execute(context.Background(), BuildExecutionRequest{
		Build:   buildResponse(),
		Message: buildRequestedMessage(false),
	}, logs)
	if err != nil {
		t.Fatalf("Execute returned error: %v", err)
	}
	emitted := drainLogMessages(logs)
	if result.Status != "failed" {
		t.Fatalf("unexpected status: %#v", result)
	}
	if !strings.Contains(result.ErrorMessage, "upload failed") {
		t.Fatalf("unexpected error message: %s", result.ErrorMessage)
	}
	if len(emitted) != 5 {
		t.Fatalf("expected 5 log lines, got %d", len(emitted))
	}
}

type stubPublisher struct {
	result artifacts.PublishResult
	err    error
	inputs []artifacts.PublishInput
	dirs   []string
}

func (s *stubPublisher) PublishSimulatedStaticRelease(input artifacts.PublishInput) (artifacts.PublishResult, error) {
	s.inputs = append(s.inputs, input)
	if s.err != nil {
		return artifacts.PublishResult{}, s.err
	}
	return s.result, nil
}

func (s *stubPublisher) PublishStaticReleaseFromDirectory(input artifacts.PublishInput, outputRoot string) (artifacts.PublishResult, error) {
	s.inputs = append(s.inputs, input)
	s.dirs = append(s.dirs, outputRoot)
	if s.err != nil {
		return artifacts.PublishResult{}, s.err
	}
	return s.result, nil
}

func buildResponse() controlplane.BuildResponse {
	return controlplane.BuildResponse{
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
	}
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

func drainLogMessages(logs chan BuildLogMessage) []BuildLogMessage {
	close(logs)
	var emitted []BuildLogMessage
	for message := range logs {
		emitted = append(emitted, message)
	}
	return emitted
}
