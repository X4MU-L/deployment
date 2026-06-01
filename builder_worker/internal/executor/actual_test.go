package executor

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"builder_worker/internal/artifacts"
)

func TestActualBuildExecutorBuildsLocalRepoAndPublishesOutput(t *testing.T) {
	requireCommand(t, "git")
	requireCommand(t, "sh")

	repoDir, commitSHA := createGitRepo(t, map[string]string{
		"README.md": "# demo\n",
	})

	publisher := &capturingPublisher{
		result: artifacts.PublishResult{
			ArtifactRef: "r2://static-artifacts/projects/project-1/releases/release-1",
			ManifestRef: "r2://static-artifacts/projects/project-1/releases/release-1/static_release_manifest.v1.json",
		},
	}
	buildExecutor := NewActualBuildExecutorWithDeps(publisher, &GitSourceFetcher{}, NewShellCommandRunner())
	logs := make(chan BuildLogMessage, 64)

	message := buildRequestedMessage(false)
	message.GitCheckout.RepoURL = repoDir
	message.GitCheckout.CommitSHA = commitSHA
	message.BuildSpec.InstallCommand = "printf 'install ok\\n'"
	message.BuildSpec.BuildCommand = "mkdir -p dist/assets && printf '<!doctype html>\\n<html><body>ok</body></html>\\n' > dist/index.html && printf 'console.log(\"ok\")\\n' > dist/assets/app.js && printf 'build ok\\n'"

	result, err := buildExecutor.Execute(context.Background(), BuildExecutionRequest{
		Build:   buildResponse(),
		Message: message,
	}, logs)
	if err != nil {
		t.Fatalf("Execute returned error: %v", err)
	}
	emitted := drainLogMessages(logs)

	if result.Status != "succeeded" {
		t.Fatalf("unexpected status: %#v", result)
	}
	if len(publisher.publishedFiles) != 1 {
		t.Fatalf("expected publisher to capture one publish payload, got %d", len(publisher.publishedFiles))
	}
	assertPublishedFile(t, publisher.publishedFiles[0], "index.html")
	assertPublishedFile(t, publisher.publishedFiles[0], "assets/app.js")
	assertContainsLog(t, emitted, "install ok")
	assertContainsLog(t, emitted, "build ok")
	assertContainsLog(t, emitted, "upload: published static release to r2://static-artifacts/projects/project-1/releases/release-1")
}

func TestActualBuildExecutorFailsWhenOutputDirectoryMissing(t *testing.T) {
	requireCommand(t, "git")
	requireCommand(t, "sh")

	repoDir, commitSHA := createGitRepo(t, map[string]string{
		"README.md": "# demo\n",
	})

	buildExecutor := NewActualBuildExecutorWithDeps(&capturingPublisher{}, &GitSourceFetcher{}, NewShellCommandRunner())
	logs := make(chan BuildLogMessage, 64)

	message := buildRequestedMessage(false)
	message.GitCheckout.RepoURL = repoDir
	message.GitCheckout.CommitSHA = commitSHA
	message.BuildSpec.InstallCommand = "printf 'install ok\\n'"
	message.BuildSpec.BuildCommand = "printf 'build ok\\n'"
	message.BuildSpec.OutputDirectory = "dist"

	result, err := buildExecutor.Execute(context.Background(), BuildExecutionRequest{
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
	if !strings.Contains(result.ErrorMessage, "output directory dist was not produced") {
		t.Fatalf("unexpected error message: %s", result.ErrorMessage)
	}
	assertContainsLog(t, emitted, "error: output directory dist was not produced by the build")
}

func TestDockerCommandRunnerBuildsExpectedDockerInvocation(t *testing.T) {
	logs := make(chan BuildLogMessage, 16)
	var capturedName string
	var capturedArgs []string

	runner := NewDockerCommandRunner("node:22-bookworm")
	runner.newExecCommand = func(_ context.Context, name string, args ...string) *exec.Cmd {
		capturedName = name
		capturedArgs = append([]string{}, args...)
		return exec.Command("sh", "-lc", "printf 'docker ok\\n'")
	}

	err := runner.Run(context.Background(), CommandRunRequest{
		Phase:   "build",
		Command: "npm run build",
		WorkDir: "/tmp/workspace",
		Env: map[string]string{
			"API_URL": "https://example.com",
			"TOKEN":   "secret",
		},
	}, logs)
	if err != nil {
		t.Fatalf("Run returned error: %v", err)
	}
	emitted := drainLogMessages(logs)

	if capturedName != "docker" {
		t.Fatalf("expected docker binary, got %q", capturedName)
	}
	assertStringSliceContains(t, capturedArgs, "run")
	assertStringSliceContains(t, capturedArgs, "--rm")
	assertStringSliceContains(t, capturedArgs, "--workdir")
	assertStringSliceContains(t, capturedArgs, "/workspace")
	assertStringSliceContains(t, capturedArgs, "--volume")
	assertStringSliceContains(t, capturedArgs, "/tmp/workspace:/workspace")
	assertStringSliceContains(t, capturedArgs, "--tmpfs")
	assertStringSliceContains(t, capturedArgs, "/tmp")
	assertStringSliceContains(t, capturedArgs, "--network")
	assertStringSliceContains(t, capturedArgs, "none")
	assertStringSliceContains(t, capturedArgs, "--read-only")
	assertStringSliceContains(t, capturedArgs, "--pids-limit")
	assertStringSliceContains(t, capturedArgs, "256")
	assertStringSliceContains(t, capturedArgs, "--cap-drop")
	assertStringSliceContains(t, capturedArgs, "ALL")
	assertStringSliceContains(t, capturedArgs, "--security-opt")
	assertStringSliceContains(t, capturedArgs, "no-new-privileges")
	assertStringSliceContains(t, capturedArgs, "--user")
	assertStringSliceContains(t, capturedArgs, formatHostUser())
	assertStringSliceContains(t, capturedArgs, "--env")
	assertStringSliceContains(t, capturedArgs, "API_URL=https://example.com")
	assertStringSliceContains(t, capturedArgs, "TOKEN=secret")
	assertStringSliceContains(t, capturedArgs, "HOME=/tmp")
	assertStringSliceContains(t, capturedArgs, "CI=true")
	assertStringSliceContains(t, capturedArgs, "node:22-bookworm")
	assertStringSliceContains(t, capturedArgs, "npm run build")
	assertContainsLog(t, emitted, "docker ok")
}

func TestDockerCommandRunnerWithConfigOverridesDefaults(t *testing.T) {
	var capturedArgs []string

	runner := NewDockerCommandRunnerWithConfig(DockerRunnerConfig{
		Image:            "custom-image",
		InstallNetwork:   "bridge",
		BuildNetwork:     "none",
		ReadOnlyRootFS:   false,
		PidsLimit:        64,
		DropCapabilities: false,
		NoNewPrivileges:  false,
		MapHostUser:      false,
	})
	runner.newExecCommand = func(_ context.Context, _ string, args ...string) *exec.Cmd {
		capturedArgs = append([]string{}, args...)
		return exec.Command("sh", "-lc", "true")
	}

	err := runner.Run(context.Background(), CommandRunRequest{
		Phase:   "install",
		Command: "npm install",
		WorkDir: "/tmp/workspace",
	}, make(chan BuildLogMessage, 1))
	if err != nil {
		t.Fatalf("Run returned error: %v", err)
	}

	assertStringSliceContains(t, capturedArgs, "--network")
	assertStringSliceContains(t, capturedArgs, "bridge")
	assertStringSliceContains(t, capturedArgs, "--pids-limit")
	assertStringSliceContains(t, capturedArgs, "64")
	assertStringSliceNotContains(t, capturedArgs, "--read-only")
	assertStringSliceNotContains(t, capturedArgs, "--cap-drop")
	assertStringSliceNotContains(t, capturedArgs, "--security-opt")
	assertStringSliceNotContains(t, capturedArgs, "--user")
	assertStringSliceContains(t, capturedArgs, "custom-image")
}

func TestDockerCommandRunnerUsesPhaseSpecificBuildNetwork(t *testing.T) {
	var capturedArgs []string

	runner := NewDockerCommandRunnerWithConfig(DockerRunnerConfig{
		Image:          "custom-image",
		InstallNetwork: "bridge",
		BuildNetwork:   "none",
	})
	runner.newExecCommand = func(_ context.Context, _ string, args ...string) *exec.Cmd {
		capturedArgs = append([]string{}, args...)
		return exec.Command("sh", "-lc", "true")
	}

	err := runner.Run(context.Background(), CommandRunRequest{
		Phase:   "build",
		Command: "npm run build",
		WorkDir: "/tmp/workspace",
	}, make(chan BuildLogMessage, 1))
	if err != nil {
		t.Fatalf("Run returned error: %v", err)
	}

	assertStringSliceContains(t, capturedArgs, "--network")
	assertStringSliceContains(t, capturedArgs, "none")
}

type capturingPublisher struct {
	result         artifacts.PublishResult
	err            error
	inputs         []artifacts.PublishInput
	publishedFiles []map[string]string
}

func (p *capturingPublisher) PublishSimulatedStaticRelease(input artifacts.PublishInput) (artifacts.PublishResult, error) {
	p.inputs = append(p.inputs, input)
	if p.err != nil {
		return artifacts.PublishResult{}, p.err
	}
	return p.result, nil
}

func (p *capturingPublisher) PublishStaticReleaseFromDirectory(input artifacts.PublishInput, outputRoot string) (artifacts.PublishResult, error) {
	p.inputs = append(p.inputs, input)
	files := make(map[string]string)
	err := filepath.Walk(outputRoot, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if info.IsDir() {
			return nil
		}
		relative, err := filepath.Rel(outputRoot, path)
		if err != nil {
			return err
		}
		content, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		files[filepath.ToSlash(relative)] = string(content)
		return nil
	})
	if err != nil {
		return artifacts.PublishResult{}, err
	}
	p.publishedFiles = append(p.publishedFiles, files)
	if p.err != nil {
		return artifacts.PublishResult{}, p.err
	}
	return p.result, nil
}

func createGitRepo(t *testing.T, files map[string]string) (string, string) {
	t.Helper()

	repoDir := t.TempDir()
	for relativePath, content := range files {
		fullPath := filepath.Join(repoDir, relativePath)
		if err := os.MkdirAll(filepath.Dir(fullPath), 0o755); err != nil {
			t.Fatalf("create repo dir: %v", err)
		}
		if err := os.WriteFile(fullPath, []byte(content), 0o644); err != nil {
			t.Fatalf("write repo file: %v", err)
		}
	}

	runGit(t, repoDir, "init")
	runGit(t, repoDir, "config", "user.email", "builder@example.com")
	runGit(t, repoDir, "config", "user.name", "Builder Worker")
	runGit(t, repoDir, "add", ".")
	runGit(t, repoDir, "commit", "-m", "initial commit")

	commitSHA := strings.TrimSpace(runGit(t, repoDir, "rev-parse", "HEAD"))
	return repoDir, commitSHA
}

func runGit(t *testing.T, workDir string, args ...string) string {
	t.Helper()

	command := exec.Command("git", args...)
	command.Dir = workDir
	output, err := command.CombinedOutput()
	if err != nil {
		t.Fatalf("git %s failed: %v\n%s", strings.Join(args, " "), err, string(output))
	}
	return string(output)
}

func requireCommand(t *testing.T, name string) {
	t.Helper()
	if _, err := exec.LookPath(name); err != nil {
		t.Skipf("%s not available: %v", name, err)
	}
}

func assertPublishedFile(t *testing.T, files map[string]string, path string) {
	t.Helper()
	if _, ok := files[path]; !ok {
		t.Fatalf("expected published files to contain %s, got %#v", path, files)
	}
}

func assertContainsLog(t *testing.T, logs []BuildLogMessage, expected string) {
	t.Helper()
	for _, logMessage := range logs {
		if strings.Contains(logMessage.Line, expected) {
			return
		}
	}
	t.Fatalf("expected logs to contain %q, got %#v", expected, logs)
}

func assertStringSliceContains(t *testing.T, values []string, expected string) {
	t.Helper()
	for _, value := range values {
		if value == expected {
			return
		}
	}
	t.Fatalf("expected %#v to contain %q", values, expected)
}

func assertStringSliceNotContains(t *testing.T, values []string, expected string) {
	t.Helper()
	for _, value := range values {
		if value == expected {
			t.Fatalf("expected %#v not to contain %q", values, expected)
		}
	}
}
