package executor

import (
	"context"
	"os/exec"
	"strings"
	"testing"
)

func TestBuildSourceFetcherDefaultsToDocker(t *testing.T) {
	fetcher, err := BuildSourceFetcher("", SourceFetcherFactoryConfig{
		DockerImage:         "alpine/git:2.47.2",
		DockerNetwork:       "bridge",
		DockerCPUs:          "1",
		DockerMemory:        "1g",
		DockerMemorySwap:    "1g",
		DockerPidsLimit:     64,
		AllowedDockerImages: []string{"alpine/git:2.47.2"},
	})
	if err != nil {
		t.Fatalf("BuildSourceFetcher returned error: %v", err)
	}
	dockerFetcher, ok := fetcher.(*DockerGitSourceFetcher)
	if !ok {
		t.Fatalf("expected docker source fetcher, got %T", fetcher)
	}
	if dockerFetcher.config.NetworkMode != "bridge" || dockerFetcher.config.CPUs != "1" || dockerFetcher.config.Memory != "1g" {
		t.Fatalf("unexpected docker fetcher config: %#v", dockerFetcher.config)
	}
}

func TestBuildSourceFetcherResolvesHost(t *testing.T) {
	fetcher, err := BuildSourceFetcher(SourceFetcherProviderHost, SourceFetcherFactoryConfig{})
	if err != nil {
		t.Fatalf("BuildSourceFetcher returned error: %v", err)
	}
	if _, ok := fetcher.(*GitSourceFetcher); !ok {
		t.Fatalf("expected git source fetcher, got %T", fetcher)
	}
}

func TestBuildSourceFetcherRejectsDisallowedImage(t *testing.T) {
	_, err := BuildSourceFetcher("", SourceFetcherFactoryConfig{
		DockerImage:         "custom-image",
		AllowedDockerImages: []string{"alpine/git:2.47.2"},
	})
	if err == nil {
		t.Fatalf("expected disallowed image error")
	}
}

func TestDockerGitSourceFetcherBuildsExpectedDockerInvocation(t *testing.T) {
	var capturedName string
	var capturedArgs []string

	fetcher := NewDockerGitSourceFetcherWithConfig(DockerGitSourceFetcherConfig{
		Image:            "alpine/git:2.47.2",
		NetworkMode:      "bridge",
		CPUs:             "1",
		Memory:           "1g",
		MemorySwap:       "1g",
		PidsLimit:        64,
		DropCapabilities: true,
		NoNewPrivileges:  true,
		MapHostUser:      false,
	})
	fetcher.newExecCommand = func(_ context.Context, name string, args ...string) *exec.Cmd {
		capturedName = name
		capturedArgs = append([]string{}, args...)
		return exec.Command("sh", "-lc", "true")
	}

	_, cleanup, err := fetcher.Fetch(context.Background(), SourceFetchRequest{
		RepoURL:       "https://github.com/example/demo",
		DefaultBranch: "main",
		CommitSHA:     "abc123",
	})
	if cleanup != nil {
		defer cleanup()
	}
	if err != nil {
		t.Fatalf("Fetch returned error: %v", err)
	}

	if capturedName != "docker" {
		t.Fatalf("expected docker binary, got %q", capturedName)
	}
	assertStringSliceContains(t, capturedArgs, "run")
	assertStringSliceContains(t, capturedArgs, "--network")
	assertStringSliceContains(t, capturedArgs, "bridge")
	assertStringSliceContains(t, capturedArgs, "--cpus")
	assertStringSliceContains(t, capturedArgs, "1")
	assertStringSliceContains(t, capturedArgs, "--memory")
	assertStringSliceContains(t, capturedArgs, "1g")
	assertStringSliceContains(t, capturedArgs, "--memory-swap")
	assertStringSliceContains(t, capturedArgs, "1g")
	assertStringSliceContains(t, capturedArgs, "--cap-drop")
	assertStringSliceContains(t, capturedArgs, "ALL")
	assertStringSliceContains(t, capturedArgs, "--security-opt")
	assertStringSliceContains(t, capturedArgs, "no-new-privileges")
	assertStringSliceContains(t, capturedArgs, "alpine/git:2.47.2")

	foundScript := false
	for _, arg := range capturedArgs {
		if strings.Contains(arg, "git init /workspace/repo") && strings.Contains(arg, "git -C /workspace/repo fetch --depth 1 --no-tags origin 'abc123'") {
			foundScript = true
			break
		}
	}
	if !foundScript {
		t.Fatalf("expected docker fetch script in args, got %#v", capturedArgs)
	}
}
