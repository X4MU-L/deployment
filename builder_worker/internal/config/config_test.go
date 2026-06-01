package config

import "testing"

func TestLoadFromEnvRejectsDockerImageOutsideAllowlist(t *testing.T) {
	t.Setenv("CP_BUILD_COMMAND_RUNNER_PROVIDER", "docker")
	t.Setenv("CP_BUILD_DOCKER_IMAGE", "custom-image")
	t.Setenv("CP_BUILD_DOCKER_ALLOWED_IMAGES", "node:20-bookworm")

	_, err := LoadFromEnv()
	if err == nil {
		t.Fatalf("expected allowlist validation error")
	}
}

func TestLoadFromEnvParsesDockerPolicySettings(t *testing.T) {
	t.Setenv("CP_BUILD_COMMAND_RUNNER_PROVIDER", "docker")
	t.Setenv("CP_BUILD_DOCKER_IMAGE", "node:20-bookworm")
	t.Setenv("CP_BUILD_DOCKER_ALLOWED_IMAGES", "node:20-bookworm, custom-image")
	t.Setenv("CP_BUILD_DOCKER_INSTALL_NETWORK", "bridge")
	t.Setenv("CP_BUILD_DOCKER_BUILD_NETWORK", "none")
	t.Setenv("CP_BUILD_DOCKER_PIDS_LIMIT", "512")

	cfg, err := LoadFromEnv()
	if err != nil {
		t.Fatalf("LoadFromEnv returned error: %v", err)
	}
	if cfg.BuildDockerInstallNet != "bridge" || cfg.BuildDockerBuildNet != "none" {
		t.Fatalf("unexpected docker networks: %#v", cfg)
	}
	if cfg.BuildDockerPidsLimit != 512 {
		t.Fatalf("unexpected docker pids limit: %#v", cfg)
	}
	if len(cfg.AllowedDockerImages) != 2 {
		t.Fatalf("unexpected docker image allowlist: %#v", cfg.AllowedDockerImages)
	}
}
