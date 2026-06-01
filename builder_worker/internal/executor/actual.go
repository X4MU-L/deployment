package executor

import (
	"context"
	"fmt"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strconv"
	"strings"

	"builder_worker/internal/artifacts"
	"builder_worker/internal/contracts"
)

type SourceFetchRequest struct {
	RepoURL       string
	DefaultBranch string
	SourceRef     string
	CommitSHA     string
}

type SourceFetcher interface {
	Fetch(context.Context, SourceFetchRequest) (string, func(), error)
}

type CommandRunRequest struct {
	Phase   string
	Command string
	WorkDir string
	Env     map[string]string
}

type CommandRunner interface {
	Run(context.Context, CommandRunRequest, chan<- BuildLogMessage) error
}

type execCommandFactory func(context.Context, string, ...string) *exec.Cmd

type DockerRunnerConfig struct {
	Image            string
	InstallNetwork   string
	BuildNetwork     string
	CPUs             string
	Memory           string
	MemorySwap       string
	ReadOnlyRootFS   bool
	PidsLimit        int
	DropCapabilities bool
	NoNewPrivileges  bool
	MapHostUser      bool
}

type ActualBuildExecutor struct {
	publisher artifacts.Publisher
	fetcher   SourceFetcher
	runner    CommandRunner
}

// NewActualBuildExecutor creates a new ActualBuildExecutor with the given artifact publisher.
// It uses a GitSourceFetcher to fetch source code from Git repositories, and a DockerCommandRunner to execute build commands inside Docker containers.
func NewActualBuildExecutor(publisher artifacts.Publisher) *ActualBuildExecutor {
	return NewActualBuildExecutorWithDeps(
		publisher,
		&GitSourceFetcher{},
		NewDockerCommandRunnerWithConfig(DockerRunnerConfig{
			Image:            "node:20-bookworm",
			InstallNetwork:   "bridge",
			BuildNetwork:     "none",
			CPUs:             "2",
			Memory:           "2g",
			MemorySwap:       "2g",
			ReadOnlyRootFS:   true,
			PidsLimit:        256,
			DropCapabilities: true,
			NoNewPrivileges:  true,
			MapHostUser:      true,
		}),
	)
}

// NewActualBuildExecutorWithDeps creates a new ActualBuildExecutor with the given dependencies.
// This is useful for testing or when you want to inject specific implementations of the dependencies.
func NewActualBuildExecutorWithDeps(publisher artifacts.Publisher, fetcher SourceFetcher, runner CommandRunner) *ActualBuildExecutor {
	return &ActualBuildExecutor{
		publisher: publisher,
		fetcher:   fetcher,
		runner:    runner,
	}
}

// Execute runs the build execution logic for the given build and message, sending logs back through the provided logSink channel.
// It performs the following steps:
// 1. Fetches the source code from the Git repository based on the information in the message.
// 2. Resolves the build workspace directory based on the root directory specified in the message or build config.
// 3. Runs the install command if it is specified, streaming logs back through logSink.
// 4. Runs the build command, streaming logs back through logSink.
// 5. Validates that the output directory was produced by the build.
// 6. Publishes the build artifacts using the artifact publisher.
// 7. Returns a BuildExecutionResult indicating success or failure, along with any relevant artifact references or error messages.
func (e *ActualBuildExecutor) Execute(ctx context.Context, request BuildExecutionRequest, logSink chan<- BuildLogMessage) (BuildExecutionResult, error) {
	build := request.Build
	message := request.Message

	repoURL := firstNonEmpty(message.GitCheckout.RepoURL, stringValue(build.SourceSnapshot["repo_url"]))
	sourceRef := firstNonEmpty(
		message.GitCheckout.CommitSHA,
		message.GitCheckout.SourceRef,
		build.SourceRef,
		message.GitCheckout.DefaultBranch,
		stringValue(build.SourceSnapshot["default_branch"]),
		"main",
	)
	rootDirectory := firstNonEmpty(message.BuildSpec.RootDirectory, stringValue(build.BuildConfig["root_directory"]))
	installCommand := strings.TrimSpace(firstNonEmpty(message.BuildSpec.InstallCommand, stringValue(build.BuildConfig["install_command"])))
	buildCommand := strings.TrimSpace(firstNonEmpty(message.BuildSpec.BuildCommand, stringValue(build.BuildConfig["build_command"])))
	outputDirectory := firstNonEmpty(message.BuildSpec.OutputDirectory, stringValue(build.BuildConfig["output_directory"]), "dist")
	projectName := firstNonEmpty(stringValue(build.SourceSnapshot["project_name"]), message.BuildID)

	if err := emitLogs(ctx, logSink,
		BuildLogMessage{Stream: "stdout", Line: fmt.Sprintf("builder: received build %s", message.BuildID)},
		BuildLogMessage{Stream: "stdout", Line: fmt.Sprintf("source: %s", repoURL)},
		BuildLogMessage{Stream: "stdout", Line: fmt.Sprintf("checkout ref: %s", sourceRef)},
	); err != nil {
		return BuildExecutionResult{}, err
	}

	supported, reason := isSupportedActualSource(build.SourceSnapshot, message, repoURL)
	if !supported {
		if err := emitLogs(ctx, logSink,
			BuildLogMessage{Stream: "stdout", Line: "repo visibility: unsupported for actual executor"},
			BuildLogMessage{Stream: "stderr", Line: fmt.Sprintf("error: %s", reason)},
		); err != nil {
			return BuildExecutionResult{}, err
		}
		return BuildExecutionResult{
			Status:       "failed",
			ErrorMessage: reason,
		}, nil
	}
	if isLocalRepoPath(repoURL) {
		if err := emitLog(ctx, logSink, "stdout", "repo visibility: local workspace override"); err != nil {
			return BuildExecutionResult{}, err
		}
	} else {
		if err := emitLog(ctx, logSink, "stdout", "repo visibility: assumed public"); err != nil {
			return BuildExecutionResult{}, err
		}
	}

	repoDir, cleanup, err := e.fetcher.Fetch(ctx, SourceFetchRequest{
		RepoURL:       repoURL,
		DefaultBranch: message.GitCheckout.DefaultBranch,
		SourceRef:     message.GitCheckout.SourceRef,
		CommitSHA:     message.GitCheckout.CommitSHA,
	})
	if err != nil {
		if logErr := emitLog(ctx, logSink, "stderr", fmt.Sprintf("error: failed to fetch source: %v", err)); logErr != nil {
			return BuildExecutionResult{}, logErr
		}
		return BuildExecutionResult{
			Status:       "failed",
			ErrorMessage: fmt.Sprintf("failed to fetch source: %v", err),
		}, nil
	}
	defer cleanup()

	buildRoot, err := resolveWorkspaceSubdir(repoDir, rootDirectory)
	if err != nil {
		if logErr := emitLog(ctx, logSink, "stderr", fmt.Sprintf("error: invalid root directory: %v", err)); logErr != nil {
			return BuildExecutionResult{}, logErr
		}
		return BuildExecutionResult{
			Status:       "failed",
			ErrorMessage: fmt.Sprintf("invalid root directory: %v", err),
		}, nil
	}
	if err := emitLog(ctx, logSink, "stdout", fmt.Sprintf("workspace: checked out repository into %s", buildRoot)); err != nil {
		return BuildExecutionResult{}, err
	}

	env := envSnapshotToStrings(message.BuildSpec.EnvSnapshot)

	if installCommand == "" {
		if err := emitLog(ctx, logSink, "stdout", "install: skipped (no install command configured)"); err != nil {
			return BuildExecutionResult{}, err
		}
	} else {
		if err := emitLog(ctx, logSink, "stdout", fmt.Sprintf("install: running %s", installCommand)); err != nil {
			return BuildExecutionResult{}, err
		}
		if err := e.runner.Run(ctx, CommandRunRequest{
			Phase:   "install",
			Command: installCommand,
			WorkDir: buildRoot,
			Env:     env,
		}, logSink); err != nil {
			if logErr := emitLog(ctx, logSink, "stderr", fmt.Sprintf("error: %v", err)); logErr != nil {
				return BuildExecutionResult{}, logErr
			}
			return BuildExecutionResult{
				Status:       "failed",
				ErrorMessage: err.Error(),
			}, nil
		}
	}

	if buildCommand == "" {
		const errorMessage = "build command is required for actual executor"
		if err := emitLog(ctx, logSink, "stderr", "error: "+errorMessage); err != nil {
			return BuildExecutionResult{}, err
		}
		return BuildExecutionResult{
			Status:       "failed",
			ErrorMessage: errorMessage,
		}, nil
	}

	if err := emitLog(ctx, logSink, "stdout", fmt.Sprintf("build: running %s", buildCommand)); err != nil {
		return BuildExecutionResult{}, err
	}
	if err := e.runner.Run(ctx, CommandRunRequest{
		Phase:   "build",
		Command: buildCommand,
		WorkDir: buildRoot,
		Env:     env,
	}, logSink); err != nil {
		if logErr := emitLog(ctx, logSink, "stderr", fmt.Sprintf("error: %v", err)); logErr != nil {
			return BuildExecutionResult{}, logErr
		}
		return BuildExecutionResult{
			Status:       "failed",
			ErrorMessage: err.Error(),
		}, nil
	}

	outputRoot, err := resolveWorkspaceSubdir(buildRoot, outputDirectory)
	if err != nil {
		if logErr := emitLog(ctx, logSink, "stderr", fmt.Sprintf("error: invalid output directory: %v", err)); logErr != nil {
			return BuildExecutionResult{}, logErr
		}
		return BuildExecutionResult{
			Status:       "failed",
			ErrorMessage: fmt.Sprintf("invalid output directory: %v", err),
		}, nil
	}
	info, err := os.Stat(outputRoot)
	if err != nil || !info.IsDir() {
		errorMessage := fmt.Sprintf("output directory %s was not produced by the build", outputDirectory)
		if statErr := emitLog(ctx, logSink, "stderr", "error: "+errorMessage); statErr != nil {
			return BuildExecutionResult{}, statErr
		}
		return BuildExecutionResult{
			Status:       "failed",
			ErrorMessage: errorMessage,
		}, nil
	}

	published, err := e.publisher.PublishStaticReleaseFromDirectory(artifacts.PublishInput{
		ProjectID:       build.ProjectID,
		BuildID:         message.BuildID,
		ReleaseID:       build.PlannedReleaseID,
		ProjectName:     projectName,
		OutputDirectory: outputDirectory,
		Bucket:          message.ArtifactTarget.Bucket,
		Prefix:          message.ArtifactTarget.Prefix,
		ManifestKey:     message.ArtifactTarget.ManifestKey,
	}, outputRoot)
	if err != nil {
		if logErr := emitLog(ctx, logSink, "stderr", fmt.Sprintf("error: failed to publish static release: %v", err)); logErr != nil {
			return BuildExecutionResult{}, logErr
		}
		return BuildExecutionResult{
			Status:       "failed",
			ErrorMessage: fmt.Sprintf("failed to publish static release: %v", err),
		}, nil
	}

	if err := emitLogs(ctx, logSink,
		BuildLogMessage{Stream: "stdout", Line: fmt.Sprintf("output: static files generated in %s", outputDirectory)},
		BuildLogMessage{Stream: "stdout", Line: fmt.Sprintf("upload: published static release to %s", published.ArtifactRef)},
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

type GitSourceFetcher struct{}

type DockerGitSourceFetcherConfig struct {
	Image            string
	NetworkMode      string
	CPUs             string
	Memory           string
	MemorySwap       string
	PidsLimit        int
	DropCapabilities bool
	NoNewPrivileges  bool
	MapHostUser      bool
}

type DockerGitSourceFetcher struct {
	config         DockerGitSourceFetcherConfig
	newExecCommand execCommandFactory
}

func (f *GitSourceFetcher) Fetch(ctx context.Context, request SourceFetchRequest) (string, func(), error) {
	tempDir, err := os.MkdirTemp("", "builder-source-*")
	if err != nil {
		return "", func() {}, fmt.Errorf("create temp workspace: %w", err)
	}
	cleanup := func() {
		_ = os.RemoveAll(tempDir)
	}

	repoDir := filepath.Join(tempDir, "repo")
	repoSource, err := normalizeRepoSource(request.RepoURL)
	if err != nil {
		cleanup()
		return "", func() {}, fmt.Errorf("normalize repo source: %w", err)
	}
	if err := runExecCommand(ctx, tempDir, nil, "git", "init", repoDir); err != nil {
		cleanup()
		return "", func() {}, fmt.Errorf("git init failed: %w", err)
	}
	ref := firstNonEmpty(request.CommitSHA, request.SourceRef, request.DefaultBranch)
	if ref == "" {
		ref = "HEAD"
	}
	if err := runExecCommand(ctx, repoDir, nil, "git", "remote", "add", "origin", repoSource); err != nil {
		cleanup()
		return "", func() {}, fmt.Errorf("git remote add failed: %w", err)
	}
	if err := runExecCommand(ctx, repoDir, nil, "git", "fetch", "--depth", "1", "--no-tags", "origin", ref); err != nil {
		cleanup()
		return "", func() {}, fmt.Errorf("git fetch %s failed: %w", ref, err)
	}
	if err := runExecCommand(ctx, repoDir, nil, "git", "checkout", "--detach", "FETCH_HEAD"); err != nil {
		cleanup()
		return "", func() {}, fmt.Errorf("git checkout FETCH_HEAD failed: %w", err)
	}

	return repoDir, cleanup, nil
}

func NewDockerGitSourceFetcherWithConfig(config DockerGitSourceFetcherConfig) *DockerGitSourceFetcher {
	if config.Image == "" {
		config.Image = "alpine/git:2.47.2"
	}
	if config.NetworkMode == "" {
		config.NetworkMode = "bridge"
	}
	if config.CPUs == "" {
		config.CPUs = "1"
	}
	if config.Memory == "" {
		config.Memory = "1g"
	}
	if config.MemorySwap == "" && config.Memory != "" {
		config.MemorySwap = config.Memory
	}
	if config.PidsLimit < 1 {
		config.PidsLimit = 128
	}
	return &DockerGitSourceFetcher{
		config:         config,
		newExecCommand: exec.CommandContext,
	}
}

func (f *DockerGitSourceFetcher) Fetch(ctx context.Context, request SourceFetchRequest) (string, func(), error) {
	tempDir, err := os.MkdirTemp("", "builder-source-*")
	if err != nil {
		return "", func() {}, fmt.Errorf("create temp workspace: %w", err)
	}
	cleanup := func() {
		_ = os.RemoveAll(tempDir)
	}

	repoDir := filepath.Join(tempDir, "repo")
	repoSource, err := normalizeRepoSource(request.RepoURL)
	if err != nil {
		cleanup()
		return "", func() {}, fmt.Errorf("normalize repo source: %w", err)
	}
	ref := firstNonEmpty(request.CommitSHA, request.SourceRef, request.DefaultBranch)
	if ref == "" {
		ref = "HEAD"
	}

	script := strings.Join([]string{
		"set -euo pipefail",
		"git init /workspace/repo",
		fmt.Sprintf("git -C /workspace/repo remote add origin %s", shellQuote(repoSource)),
		fmt.Sprintf("git -C /workspace/repo fetch --depth 1 --no-tags origin %s", shellQuote(ref)),
		"git -C /workspace/repo checkout --detach FETCH_HEAD",
	}, "\n")

	args := []string{
		"run",
		"--rm",
		"--workdir",
		"/workspace",
		"--volume",
		tempDir + ":/workspace",
		"--tmpfs",
		"/tmp",
		"--env",
		"HOME=/tmp",
	}
	if f.config.NetworkMode != "" {
		args = append(args, "--network", f.config.NetworkMode)
	}
	if f.config.CPUs != "" {
		args = append(args, "--cpus", f.config.CPUs)
	}
	if f.config.Memory != "" {
		args = append(args, "--memory", f.config.Memory)
	}
	if f.config.MemorySwap != "" {
		args = append(args, "--memory-swap", f.config.MemorySwap)
	}
	if f.config.PidsLimit > 0 {
		args = append(args, "--pids-limit", strconv.Itoa(f.config.PidsLimit))
	}
	if f.config.DropCapabilities {
		args = append(args, "--cap-drop", "ALL")
	}
	if f.config.NoNewPrivileges {
		args = append(args, "--security-opt", "no-new-privileges")
	}
	if f.config.MapHostUser {
		args = append(args, "--user", formatHostUser())
	}
	args = append(args, f.config.Image, "sh", "-lc", script)

	command := f.newExecCommand(ctx, "docker", args...)
	output, err := command.CombinedOutput()
	if err != nil {
		cleanup()
		return "", func() {}, fmt.Errorf("dockerized git fetch failed: %w: %s", err, strings.TrimSpace(string(output)))
	}

	return repoDir, cleanup, nil
}

type ShellCommandRunner struct{}

type DockerCommandRunner struct {
	config         DockerRunnerConfig
	newExecCommand execCommandFactory
}

// NewShellCommandRunner creates a new ShellCommandRunner, which executes commands directly on the host machine.
func NewShellCommandRunner() *ShellCommandRunner {
	return &ShellCommandRunner{}
}

func (r *ShellCommandRunner) Run(ctx context.Context, request CommandRunRequest, logSink chan<- BuildLogMessage) error {
	command := exec.CommandContext(ctx, "sh", "-lc", request.Command)
	command.Dir = request.WorkDir
	command.Env = append(os.Environ(), buildEnvList(request.Env)...)
	return runStreamingCommand(ctx, command, request.Phase, logSink)
}

func NewDockerCommandRunner(image string) *DockerCommandRunner {
	return NewDockerCommandRunnerWithConfig(DockerRunnerConfig{
		Image:            image,
		InstallNetwork:   "bridge",
		BuildNetwork:     "none",
		CPUs:             "2",
		Memory:           "2g",
		MemorySwap:       "2g",
		ReadOnlyRootFS:   true,
		PidsLimit:        256,
		DropCapabilities: true,
		NoNewPrivileges:  true,
		MapHostUser:      true,
	})
}

// NewDockerCommandRunnerWithConfig creates a new DockerCommandRunner with the given configuration.
// This allows for more fine-grained control over the Docker execution environment, such as network settings, resource limits, and security options.
func NewDockerCommandRunnerWithConfig(config DockerRunnerConfig) *DockerCommandRunner {
	if config.Image == "" {
		config.Image = "node:20-bookworm"
	}
	if config.InstallNetwork == "" {
		config.InstallNetwork = "bridge"
	}
	if config.BuildNetwork == "" {
		config.BuildNetwork = "none"
	}
	if config.CPUs == "" {
		config.CPUs = "2"
	}
	if config.Memory == "" {
		config.Memory = "2g"
	}
	if config.MemorySwap == "" && config.Memory != "" {
		config.MemorySwap = config.Memory
	}
	if config.PidsLimit < 1 {
		config.PidsLimit = 256
	}
	return &DockerCommandRunner{
		config:         config,
		newExecCommand: exec.CommandContext,
	}
}

func (r *DockerCommandRunner) Run(ctx context.Context, request CommandRunRequest, logSink chan<- BuildLogMessage) error {
	args := []string{
		"run",
		"--rm",
		"--workdir",
		"/workspace",
		"--volume",
		request.WorkDir + ":/workspace",
		"--tmpfs",
		"/tmp",
		"--env",
		"HOME=/tmp",
		"--env",
		"CI=true",
	}
	if networkMode := r.networkModeForPhase(request.Phase); networkMode != "" {
		args = append(args, "--network", networkMode)
	}
	if r.config.CPUs != "" {
		args = append(args, "--cpus", r.config.CPUs)
	}
	if r.config.Memory != "" {
		args = append(args, "--memory", r.config.Memory)
	}
	if r.config.MemorySwap != "" {
		args = append(args, "--memory-swap", r.config.MemorySwap)
	}
	if r.config.ReadOnlyRootFS {
		args = append(args, "--read-only")
	}
	if r.config.PidsLimit > 0 {
		args = append(args, "--pids-limit", strconv.Itoa(r.config.PidsLimit))
	}
	if r.config.DropCapabilities {
		args = append(args, "--cap-drop", "ALL")
	}
	if r.config.NoNewPrivileges {
		args = append(args, "--security-opt", "no-new-privileges")
	}
	if r.config.MapHostUser {
		args = append(args, "--user", formatHostUser())
	}
	for _, envVar := range buildEnvList(request.Env) {
		args = append(args, "--env", envVar)
	}
	args = append(args, r.config.Image, "sh", "-lc", request.Command)

	command := r.newExecCommand(ctx, "docker", args...)
	return runStreamingCommand(ctx, command, request.Phase, logSink)
}

func (r *DockerCommandRunner) networkModeForPhase(phase string) string {
	switch phase {
	case "install":
		return r.config.InstallNetwork
	case "build":
		return r.config.BuildNetwork
	default:
		if r.config.BuildNetwork != "" {
			return r.config.BuildNetwork
		}
		return r.config.InstallNetwork
	}
}

type lineEmitter struct {
	ctx     context.Context
	logSink chan<- BuildLogMessage
	stream  string
	buffer  strings.Builder
}

func newLineEmitter(ctx context.Context, logSink chan<- BuildLogMessage, stream string) *lineEmitter {
	return &lineEmitter{
		ctx:     ctx,
		logSink: logSink,
		stream:  stream,
	}
}

func (w *lineEmitter) Write(data []byte) (int, error) {
	w.buffer.Write(data)
	for {
		content := w.buffer.String()
		index := strings.IndexByte(content, '\n')
		if index == -1 {
			return len(data), nil
		}
		line := strings.TrimSuffix(content[:index], "\r")
		w.buffer.Reset()
		w.buffer.WriteString(content[index+1:])
		if err := emitLog(w.ctx, w.logSink, w.stream, line); err != nil {
			return 0, err
		}
	}
}

func (w *lineEmitter) Flush() error {
	if w.buffer.Len() == 0 {
		return nil
	}
	line := strings.TrimSuffix(w.buffer.String(), "\r")
	w.buffer.Reset()
	return emitLog(w.ctx, w.logSink, w.stream, line)
}

func resolveWorkspaceSubdir(baseDir string, subdir string) (string, error) {
	if subdir == "" {
		return baseDir, nil
	}
	cleaned := filepath.Clean(subdir)
	if filepath.IsAbs(cleaned) || cleaned == ".." || strings.HasPrefix(cleaned, ".."+string(filepath.Separator)) {
		return "", fmt.Errorf("path must stay within workspace: %s", subdir)
	}
	return filepath.Join(baseDir, cleaned), nil
}

func envSnapshotToStrings(snapshot map[string]any) map[string]string {
	env := make(map[string]string, len(snapshot))
	for key, value := range snapshot {
		stringValue, ok := value.(string)
		if !ok {
			continue
		}
		env[key] = stringValue
	}
	return env
}

func buildEnvList(env map[string]string) []string {
	if len(env) == 0 {
		return nil
	}
	result := make([]string, 0, len(env))
	for key, value := range env {
		result = append(result, key+"="+value)
	}
	sort.Strings(result)
	return result
}

func isSupportedActualSource(sourceSnapshot map[string]any, message contracts.BuildRequestedMessage, repoURL string) (bool, string) {
	if isLocalRepoPath(repoURL) {
		return true, ""
	}
	parsed, err := url.Parse(repoURL)
	if err != nil {
		return false, "actual executor currently supports only public https://github.com repos"
	}
	if parsed.Scheme != "https" || parsed.Host != "github.com" || parsed.Path == "" || parsed.Path == "/" {
		return false, "actual executor currently supports only public https://github.com repos"
	}

	repository := message.GitCheckout.Repository
	if len(repository) == 0 {
		repository = nestedMap(sourceSnapshot, "source_repository")
	}
	if privateValue, ok := repository["private"].(bool); ok && privateValue {
		return false, "private repositories are not supported in the actual executor flow"
	}
	return true, ""
}

func isLocalRepoPath(repoURL string) bool {
	return filepath.IsAbs(repoURL) || strings.HasPrefix(repoURL, "file://")
}

func normalizeRepoSource(repoURL string) (string, error) {
	if strings.HasPrefix(repoURL, "file://") {
		parsed, err := url.Parse(repoURL)
		if err != nil {
			return "", err
		}
		return parsed.Path, nil
	}
	return repoURL, nil
}

func shellQuote(value string) string {
	return "'" + strings.ReplaceAll(value, "'", `'"'"'`) + "'"
}

func runExecCommand(ctx context.Context, workDir string, env []string, name string, args ...string) error {
	command := exec.CommandContext(ctx, name, args...)
	command.Dir = workDir
	command.Env = append(os.Environ(), env...)
	output, err := command.CombinedOutput()
	if err != nil {
		return fmt.Errorf("%w: %s", err, strings.TrimSpace(string(output)))
	}
	return nil
}

func firstError(errors ...error) error {
	for _, err := range errors {
		if err != nil {
			return err
		}
	}
	return nil
}

func formatHostUser() string {
	return strconv.Itoa(os.Getuid()) + ":" + strconv.Itoa(os.Getgid())
}

func runStreamingCommand(ctx context.Context, command *exec.Cmd, phase string, logSink chan<- BuildLogMessage) error {
	stdoutEmitter := newLineEmitter(ctx, logSink, "stdout")
	stderrEmitter := newLineEmitter(ctx, logSink, "stderr")
	command.Stdout = stdoutEmitter
	command.Stderr = stderrEmitter

	err := command.Run()
	flushErr := firstError(stdoutEmitter.Flush(), stderrEmitter.Flush())
	if err != nil {
		if flushErr != nil {
			return flushErr
		}
		return fmt.Errorf("%s command failed: %w", phase, err)
	}
	if flushErr != nil {
		return flushErr
	}
	return nil
}
