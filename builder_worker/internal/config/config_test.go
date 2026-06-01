package config

import (
	"testing"
	"time"
)

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
	t.Setenv("CP_CLOUDFLARE_PULL_MAX_CONCURRENT_BUILDS", "4")
	t.Setenv("CP_BUILD_CLAIM_LEASE_SECONDS", "600")
	t.Setenv("CP_BUILD_CLAIM_RENEW_INTERVAL_SECONDS", "120")
	t.Setenv("CP_BUILD_MAX_DURATION_SECONDS", "540")

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
	if cfg.PullMaxConcurrentBuilds != 4 {
		t.Fatalf("unexpected max concurrent builds: %#v", cfg)
	}
	if cfg.BuildClaimLeaseSeconds != 600 || cfg.BuildClaimRenewInterval != 120*time.Second {
		t.Fatalf("unexpected claim lease settings: %#v", cfg)
	}
	if cfg.BuildMaxDuration != 540*time.Second {
		t.Fatalf("unexpected build max duration: %#v", cfg)
	}
	if len(cfg.AllowedDockerImages) != 3 {
		t.Fatalf("unexpected docker image allowlist: %#v", cfg.AllowedDockerImages)
	}
}

func TestLoadFromEnvDefaultsVisibilityTimeoutToClaimLease(t *testing.T) {
	t.Setenv("CP_CLOUDFLARE_PULL_VISIBILITY_TIMEOUT_MS", "")
	t.Setenv("CP_BUILD_CLAIM_LEASE_SECONDS", "120")
	t.Setenv("CP_BUILD_CLAIM_RENEW_INTERVAL_SECONDS", "60")
	t.Setenv("CP_BUILD_MAX_DURATION_SECONDS", "90")
	t.Setenv("CP_SOURCE_FETCHER_PROVIDER", "host")
	t.Setenv("CP_BUILD_DOCKER_ALLOWED_IMAGES", "node:20-bookworm")

	cfg, err := LoadFromEnv()
	if err != nil {
		t.Fatalf("LoadFromEnv returned error: %v", err)
	}
	if cfg.PullVisibilityTimeoutMS != 120000 {
		t.Fatalf("unexpected derived visibility timeout: %#v", cfg.PullVisibilityTimeoutMS)
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

func TestLoadFromEnvRejectsInvalidMaxConcurrentBuilds(t *testing.T) {
	t.Setenv("CP_CLOUDFLARE_PULL_MAX_CONCURRENT_BUILDS", "0")

	_, err := LoadFromEnv()
	if err == nil {
		t.Fatalf("expected max concurrent builds validation error")
	}
}

func TestLoadFromEnvRejectsRenewIntervalAtOrAboveLease(t *testing.T) {
	t.Setenv("CP_BUILD_CLAIM_LEASE_SECONDS", "60")
	t.Setenv("CP_BUILD_CLAIM_RENEW_INTERVAL_SECONDS", "60")

	_, err := LoadFromEnv()
	if err == nil {
		t.Fatalf("expected lease renewal validation error")
	}
}

func TestLoadFromEnvRejectsVisibilityTimeoutShorterThanClaimLease(t *testing.T) {
	t.Setenv("CP_BUILD_CLAIM_LEASE_SECONDS", "120")
	t.Setenv("CP_CLOUDFLARE_PULL_VISIBILITY_TIMEOUT_MS", "60000")

	_, err := LoadFromEnv()
	if err == nil {
		t.Fatalf("expected visibility timeout validation error")
	}
}

func TestLoadFromEnvRejectsBuildMaxDurationAtOrAboveClaimLease(t *testing.T) {
	t.Setenv("CP_BUILD_CLAIM_LEASE_SECONDS", "120")
	t.Setenv("CP_BUILD_CLAIM_RENEW_INTERVAL_SECONDS", "60")
	t.Setenv("CP_BUILD_MAX_DURATION_SECONDS", "120")

	_, err := LoadFromEnv()
	if err == nil {
		t.Fatalf("expected build max duration validation error")
	}
}
