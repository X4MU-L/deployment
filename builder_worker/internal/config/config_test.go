package config

import "testing"

func TestLoadFromEnvRejectsDockerImageOutsideAllowlist(t *testing.T) {
	t.Setenv("CP_BUILD_COMMAND_RUNNER_PROVIDER", "docker")
	t.Setenv("CP_BUILD_DOCKER_IMAGE", "custom-image")
	t.Setenv("CP_SOURCE_FETCHER_PROVIDER", "host")
	t.Setenv("CP_BUILD_DOCKER_ALLOWED_IMAGES", "node:20-bookworm")

	_, err := LoadFromEnv()
	if err == nil {
		t.Fatalf("expected allowlist validation error")
	}
}

func TestLoadFromEnvParsesDockerPolicySettings(t *testing.T) {
	t.Setenv("CP_BUILD_COMMAND_RUNNER_PROVIDER", "docker")
	t.Setenv("CP_BUILD_DOCKER_IMAGE", "node:20-bookworm")
	t.Setenv("CP_SOURCE_FETCHER_PROVIDER", "docker")
	t.Setenv("CP_FETCH_DOCKER_IMAGE", "alpine/git:2.47.2")
	t.Setenv("CP_BUILD_DOCKER_ALLOWED_IMAGES", "node:20-bookworm, custom-image, alpine/git:2.47.2")
	t.Setenv("CP_FETCH_DOCKER_CPUS", "0.5")
	t.Setenv("CP_FETCH_DOCKER_MEMORY", "512m")
	t.Setenv("CP_FETCH_DOCKER_MEMORY_SWAP", "512m")
	t.Setenv("CP_FETCH_DOCKER_PIDS_LIMIT", "64")
	t.Setenv("CP_BUILD_DOCKER_INSTALL_NETWORK", "bridge")
	t.Setenv("CP_BUILD_DOCKER_BUILD_NETWORK", "none")
	t.Setenv("CP_BUILD_DOCKER_CPUS", "1.5")
	t.Setenv("CP_BUILD_DOCKER_MEMORY", "1g")
	t.Setenv("CP_BUILD_DOCKER_MEMORY_SWAP", "1g")
	t.Setenv("CP_BUILD_DOCKER_PIDS_LIMIT", "512")

	cfg, err := LoadFromEnv()
	if err != nil {
		t.Fatalf("LoadFromEnv returned error: %v", err)
	}
	if cfg.BuildDockerInstallNet != "bridge" || cfg.BuildDockerBuildNet != "none" {
		t.Fatalf("unexpected docker networks: %#v", cfg)
	}
	if cfg.FetchDockerCPUs != "0.5" || cfg.FetchDockerMemory != "512m" || cfg.FetchDockerMemorySwap != "512m" || cfg.FetchDockerPidsLimit != 64 {
		t.Fatalf("unexpected fetch docker settings: %#v", cfg)
	}
	if cfg.BuildDockerCPUs != "1.5" || cfg.BuildDockerMemory != "1g" || cfg.BuildDockerMemorySwap != "1g" {
		t.Fatalf("unexpected docker resource settings: %#v", cfg)
	}
	if cfg.BuildDockerPidsLimit != 512 {
		t.Fatalf("unexpected docker pids limit: %#v", cfg)
	}
	if len(cfg.AllowedDockerImages) != 3 {
		t.Fatalf("unexpected docker image allowlist: %#v", cfg.AllowedDockerImages)
	}
}

func TestLoadFromEnvRejectsInvalidDockerCPUs(t *testing.T) {
	t.Setenv("CP_BUILD_COMMAND_RUNNER_PROVIDER", "docker")
	t.Setenv("CP_BUILD_DOCKER_IMAGE", "node:20-bookworm")
	t.Setenv("CP_SOURCE_FETCHER_PROVIDER", "host")
	t.Setenv("CP_BUILD_DOCKER_ALLOWED_IMAGES", "node:20-bookworm")
	t.Setenv("CP_BUILD_DOCKER_CPUS", "not-a-number")

	_, err := LoadFromEnv()
	if err == nil {
		t.Fatalf("expected docker cpu validation error")
	}
}

func TestLoadFromEnvRejectsDisallowedFetchImage(t *testing.T) {
	t.Setenv("CP_SOURCE_FETCHER_PROVIDER", "docker")
	t.Setenv("CP_FETCH_DOCKER_IMAGE", "custom-fetch-image")
	t.Setenv("CP_BUILD_DOCKER_ALLOWED_IMAGES", "node:20-bookworm,alpine/git:2.47.2")

	_, err := LoadFromEnv()
	if err == nil {
		t.Fatalf("expected fetch image allowlist validation error")
	}
}
