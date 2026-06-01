package executor

import (
	"context"
	"fmt"
	"net/url"

	"builder_worker/internal/artifacts"
	"builder_worker/internal/contracts"
)

type SimulatedBuildExecutor struct {
	publisher artifacts.Publisher
}

// NewSimulatedBuildExecutor creates a new instance of SimulatedBuildExecutor with the given artifact publisher.

func NewSimulatedBuildExecutor(publisher artifacts.Publisher) *SimulatedBuildExecutor {
	return &SimulatedBuildExecutor{publisher: publisher}
}

// Execute simulates the execution of a build by emitting log messages and publishing a static release using the artifact publisher.
// It checks if the repository is a supported public GitHub repository, and if so, it simulates the build process and publishes the artifacts.
// If the repository is not supported or if there is an error during publishing, it returns a failed result with an appropriate error message.
func (e *SimulatedBuildExecutor) Execute(ctx context.Context, request BuildExecutionRequest, logSink chan<- BuildLogMessage) (BuildExecutionResult, error) {
	build := request.Build
	message := request.Message

	repoURL := message.GitCheckout.RepoURL
	if repoURL == "" {
		repoURL = stringValue(build.SourceSnapshot["repo_url"])
	}
	sourceRef := firstNonEmpty(
		message.GitCheckout.SourceRef,
		build.SourceRef,
		message.GitCheckout.DefaultBranch,
		stringValue(build.SourceSnapshot["default_branch"]),
		"main",
	)
	outputDirectory := firstNonEmpty(message.BuildSpec.OutputDirectory, stringValue(build.BuildConfig["output_directory"]), "dist")
	projectName := firstNonEmpty(stringValue(build.SourceSnapshot["project_name"]), message.BuildID)

	logLines := []BuildLogMessage{
		{Stream: "stdout", Line: fmt.Sprintf("builder: received build %s", message.BuildID)},
		{Stream: "stdout", Line: fmt.Sprintf("source: %s", repoURL)},
		{Stream: "stdout", Line: fmt.Sprintf("checkout ref: %s", sourceRef)},
	}
	if err := emitLogs(ctx, logSink, logLines...); err != nil {
		return BuildExecutionResult{}, err
	}

	supported, reason := isSupportedPublicGithubRepo(build.SourceSnapshot, message, repoURL)
	if !supported {
		if err := emitLogs(ctx, logSink,
			BuildLogMessage{Stream: "stdout", Line: "repo visibility: unsupported for simulated builder"},
			BuildLogMessage{Stream: "stderr", Line: fmt.Sprintf("error: %s", reason)},
		); err != nil {
			return BuildExecutionResult{}, err
		}
		return BuildExecutionResult{
			Status:       "failed",
			ErrorMessage: reason,
		}, nil
	}

	published, err := e.publisher.PublishSimulatedStaticRelease(artifacts.PublishInput{
		ProjectID:       build.ProjectID,
		BuildID:         message.BuildID,
		ReleaseID:       build.PlannedReleaseID,
		ProjectName:     projectName,
		OutputDirectory: outputDirectory,
		Bucket:          message.ArtifactTarget.Bucket,
		Prefix:          message.ArtifactTarget.Prefix,
		ManifestKey:     message.ArtifactTarget.ManifestKey,
	})
	if err != nil {
		if err := emitLogs(ctx, logSink,
			BuildLogMessage{Stream: "stdout", Line: "repo visibility: assumed public"},
			BuildLogMessage{Stream: "stderr", Line: fmt.Sprintf("error: failed to publish simulated release: %v", err)},
		); err != nil {
			return BuildExecutionResult{}, err
		}
		return BuildExecutionResult{
			Status:       "failed",
			ErrorMessage: fmt.Sprintf("failed to publish simulated release: %v", err),
		}, nil
	}

	if err := emitLogs(ctx, logSink,
		BuildLogMessage{Stream: "stdout", Line: "repo visibility: assumed public"},
		BuildLogMessage{Stream: "stdout", Line: "install: simulated dependency install completed"},
		BuildLogMessage{Stream: "stdout", Line: "build: simulated static site build completed"},
		BuildLogMessage{Stream: "stdout", Line: fmt.Sprintf("output: simulated static files generated in %s", outputDirectory)},
		BuildLogMessage{Stream: "stdout", Line: fmt.Sprintf("upload: published simulated static release to %s", published.ArtifactRef)},
		BuildLogMessage{Stream: "stdout", Line: "upload: generated static_release_manifest.v1"},
	); err != nil {
		return BuildExecutionResult{}, err
	}
	return BuildExecutionResult{
		Status:      "succeeded",
		ArtifactRef: published.ArtifactRef,
		ManifestRef: published.ManifestRef,
	}, nil
}

func emitLogs(ctx context.Context, logSink chan<- BuildLogMessage, messages ...BuildLogMessage) error {
	for _, message := range messages {
		if err := emitLog(ctx, logSink, message.Stream, message.Line); err != nil {
			return err
		}
	}
	return nil
}

func emitLog(ctx context.Context, logSink chan<- BuildLogMessage, stream string, line string) error {
	select {
	case <-ctx.Done():
		return ctx.Err()
	case logSink <- BuildLogMessage{Stream: stream, Line: line}:
		return nil
	}
}

func isSupportedPublicGithubRepo(sourceSnapshot map[string]any, message contracts.BuildRequestedMessage, repoURL string) (bool, string) {
	parsed, err := url.Parse(repoURL)
	if err != nil {
		return false, "simulated builder currently supports only public https://github.com repos"
	}
	if parsed.Scheme != "https" || parsed.Host != "github.com" {
		return false, "simulated builder currently supports only public https://github.com repos"
	}
	if parsed.Path == "" || parsed.Path == "/" {
		return false, "repo URL must include owner and repository name"
	}

	repository := message.GitCheckout.Repository
	if repository == nil {
		repository = nestedMap(sourceSnapshot, "source_repository")
	}
	if privateValue, ok := repository["private"].(bool); ok && privateValue {
		return false, "private repositories are not supported in the simulated builder flow"
	}
	return true, ""
}

func stringValue(value any) string {
	stringValue, ok := value.(string)
	if !ok {
		return ""
	}
	return stringValue
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if value != "" {
			return value
		}
	}
	return ""
}

func nestedMap(values map[string]any, key string) map[string]any {
	if values == nil {
		return map[string]any{}
	}
	if nested, ok := values[key].(map[string]any); ok {
		return nested
	}
	return map[string]any{}
}
