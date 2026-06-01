package executor

import "testing"

func TestBuildCommandRunnerDefaultsToDocker(t *testing.T) {
	runner, err := BuildCommandRunner("", CommandRunnerFactoryConfig{
		DockerImage:          "node:20-bookworm",
		DockerInstallNetwork: "bridge",
		DockerBuildNetwork:   "none",
		DockerPidsLimit:      32,
		AllowedDockerImages:  []string{"node:20-bookworm"},
	})
	if err != nil {
		t.Fatalf("BuildCommandRunner returned error: %v", err)
	}
	dockerRunner, ok := runner.(*DockerCommandRunner)
	if !ok {
		t.Fatalf("expected docker runner, got %T", runner)
	}
	if dockerRunner.config.InstallNetwork != "bridge" || dockerRunner.config.BuildNetwork != "none" || dockerRunner.config.PidsLimit != 32 {
		t.Fatalf("unexpected docker runner config: %#v", dockerRunner.config)
	}
}

func TestBuildCommandRunnerResolvesShell(t *testing.T) {
	runner, err := BuildCommandRunner(CommandRunnerProviderShell, CommandRunnerFactoryConfig{})
	if err != nil {
		t.Fatalf("BuildCommandRunner returned error: %v", err)
	}
	if _, ok := runner.(*ShellCommandRunner); !ok {
		t.Fatalf("expected shell runner, got %T", runner)
	}
}

func TestBuildCommandRunnerRejectsDisallowedImage(t *testing.T) {
	_, err := BuildCommandRunner("", CommandRunnerFactoryConfig{
		DockerImage:         "custom-image",
		AllowedDockerImages: []string{"node:20-bookworm"},
	})
	if err == nil {
		t.Fatalf("expected disallowed image error")
	}
}
