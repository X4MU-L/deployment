package config

import (
	"fmt"
	"os"
	"slices"
	"strconv"
	"strings"
	"time"

	"github.com/joho/godotenv"
)

type Config struct {
	CloudflareAPIBaseURL    string
	CloudflareAccountID     string
	CloudflareAPIToken      string
	CloudflareQueueID       string
	LogLevel                string
	LogColor                string
	PullBatchSize           int
	PullVisibilityTimeoutMS int
	PullPollInterval        time.Duration
	PullMaxAttempts         int
	PullMaxConcurrentBuilds int
	BuildClaimLeaseSeconds  int
	BuildClaimRenewInterval time.Duration
	BuildMaxDuration        time.Duration
	ControlPlaneBaseURL     string
	InternalServiceToken    string
	ServiceName             string
	BuildExecutorProvider   string
	SourceFetcherProvider   string
	FetchDockerImage        string
	FetchDockerNetwork      string
	FetchDockerCPUs         string
	FetchDockerMemory       string
	FetchDockerMemorySwap   string
	FetchDockerPidsLimit    int
	CommandRunnerProvider   string
	BuildDockerImage        string
	BuildDockerInstallNet   string
	BuildDockerBuildNet     string
	BuildDockerCPUs         string
	BuildDockerMemory       string
	BuildDockerMemorySwap   string
	BuildDockerPidsLimit    int
	AllowedDockerImages     []string
	ArtifactStoreProvider   string
	ArtifactStoreRoot       string
	R2EndpointURL           string
	R2AccessKeyID           string
	R2SecretAccessKey       string
	R2SessionToken          string
	R2Region                string
	RunOnce                 bool
}

func LoadFromEnv() (Config, error) {

	// Load the .env file
	err := godotenv.Load()
	if err != nil && !os.IsNotExist(err) {
		return Config{}, fmt.Errorf("load .env: %w", err)
	}

	cfg := Config{
		CloudflareAPIBaseURL:    envOrDefault("CP_CLOUDFLARE_API_BASE_URL", "https://api.cloudflare.com/client/v4"),
		CloudflareAccountID:     os.Getenv("CP_CLOUDFLARE_ACCOUNT_ID"),
		CloudflareAPIToken:      os.Getenv("CP_CLOUDFLARE_API_TOKEN"),
		CloudflareQueueID:       os.Getenv("CP_CLOUDFLARE_QUEUE_ID"),
		LogLevel:                envOrDefault("CP_LOG_LEVEL", "info"),
		LogColor:                envOrDefault("CP_LOG_COLOR", "auto"),
		PullBatchSize:           intEnv("CP_CLOUDFLARE_PULL_BATCH_SIZE", 5),
		PullPollInterval:        time.Duration(intEnv("CP_CLOUDFLARE_PULL_POLL_INTERVAL_SECONDS", 5)) * time.Second,
		PullMaxAttempts:         intEnv("CP_CLOUDFLARE_PULL_MAX_ATTEMPTS", 3),
		PullMaxConcurrentBuilds: intEnv("CP_CLOUDFLARE_PULL_MAX_CONCURRENT_BUILDS", 2),
		BuildClaimLeaseSeconds:  intEnv("CP_BUILD_CLAIM_LEASE_SECONDS", 900),
		BuildClaimRenewInterval: time.Duration(intEnv("CP_BUILD_CLAIM_RENEW_INTERVAL_SECONDS", 300)) * time.Second,
		BuildMaxDuration:        time.Duration(intEnv("CP_BUILD_MAX_DURATION_SECONDS", 840)) * time.Second,
		ControlPlaneBaseURL:     envOrDefault("CP_CELERY_BUILDER_BASE_URL", "http://localhost:8000"),
		InternalServiceToken:    envOrDefault("CP_INTERNAL_SERVICE_TOKEN", "dev-internal-service-token"),
		ServiceName:             envOrDefault("CP_CELERY_BUILDER_SERVICE_NAME", "cloudflare-builder-worker"),
		BuildExecutorProvider:   envOrDefault("CP_BUILD_EXECUTOR_PROVIDER", "simulated"),
		SourceFetcherProvider:   envOrDefault("CP_SOURCE_FETCHER_PROVIDER", "docker"),
		FetchDockerImage:        envOrDefault("CP_FETCH_DOCKER_IMAGE", "alpine/git:2.47.2"),
		FetchDockerNetwork:      envOrDefault("CP_FETCH_DOCKER_NETWORK", "bridge"),
		FetchDockerCPUs:         envOrDefault("CP_FETCH_DOCKER_CPUS", "1"),
		FetchDockerMemory:       envOrDefault("CP_FETCH_DOCKER_MEMORY", "1g"),
		FetchDockerMemorySwap:   envOrDefault("CP_FETCH_DOCKER_MEMORY_SWAP", "1g"),
		FetchDockerPidsLimit:    intEnv("CP_FETCH_DOCKER_PIDS_LIMIT", 128),
		CommandRunnerProvider:   envOrDefault("CP_BUILD_COMMAND_RUNNER_PROVIDER", "docker"),
		BuildDockerImage:        envOrDefault("CP_BUILD_DOCKER_IMAGE", "node:20-bookworm"),
		BuildDockerInstallNet:   envOrDefault("CP_BUILD_DOCKER_INSTALL_NETWORK", "bridge"),
		BuildDockerBuildNet:     envOrDefault("CP_BUILD_DOCKER_BUILD_NETWORK", "none"),
		BuildDockerCPUs:         envOrDefault("CP_BUILD_DOCKER_CPUS", "2"),
		BuildDockerMemory:       envOrDefault("CP_BUILD_DOCKER_MEMORY", "2g"),
		BuildDockerMemorySwap:   envOrDefault("CP_BUILD_DOCKER_MEMORY_SWAP", "2g"),
		BuildDockerPidsLimit:    intEnv("CP_BUILD_DOCKER_PIDS_LIMIT", 256),
		AllowedDockerImages:     csvEnv("CP_BUILD_DOCKER_ALLOWED_IMAGES", []string{"node:20-bookworm"}),
		ArtifactStoreProvider:   envOrDefault("CP_ARTIFACT_STORE_PROVIDER", "local"),
		ArtifactStoreRoot:       envOrDefault("CP_ARTIFACT_STORE_ROOT", "./.artifacts"),
		R2EndpointURL:           os.Getenv("CP_R2_ENDPOINT_URL"),
		R2AccessKeyID:           os.Getenv("CP_R2_ACCESS_KEY_ID"),
		R2SecretAccessKey:       os.Getenv("CP_R2_SECRET_ACCESS_KEY"),
		R2SessionToken:          os.Getenv("CP_R2_SESSION_TOKEN"),
		R2Region:                envOrDefault("CP_R2_REGION_NAME", "auto"),
		RunOnce:                 boolEnv("CP_CLOUDFLARE_PULL_RUN_ONCE", false),
	}

	cfg.PullVisibilityTimeoutMS = intEnv(
		"CP_CLOUDFLARE_PULL_VISIBILITY_TIMEOUT_MS",
		cfg.BuildClaimLeaseSeconds*1000,
	)

	if cfg.PullBatchSize < 1 {
		return Config{}, fmt.Errorf("CP_CLOUDFLARE_PULL_BATCH_SIZE must be >= 1")
	}
	if cfg.PullVisibilityTimeoutMS < 1000 {
		return Config{}, fmt.Errorf("CP_CLOUDFLARE_PULL_VISIBILITY_TIMEOUT_MS must be >= 1000")
	}
	if cfg.PullMaxAttempts < 1 {
		return Config{}, fmt.Errorf("CP_CLOUDFLARE_PULL_MAX_ATTEMPTS must be >= 1")
	}
	if cfg.PullMaxConcurrentBuilds < 1 {
		return Config{}, fmt.Errorf("CP_CLOUDFLARE_PULL_MAX_CONCURRENT_BUILDS must be >= 1")
	}
	if cfg.BuildClaimLeaseSeconds < 1 {
		return Config{}, fmt.Errorf("CP_BUILD_CLAIM_LEASE_SECONDS must be >= 1")
	}
	if cfg.BuildClaimRenewInterval <= 0 {
		return Config{}, fmt.Errorf("CP_BUILD_CLAIM_RENEW_INTERVAL_SECONDS must be >= 1")
	}
	if cfg.BuildMaxDuration <= 0 {
		return Config{}, fmt.Errorf("CP_BUILD_MAX_DURATION_SECONDS must be >= 1")
	}
	if cfg.BuildClaimRenewInterval >= time.Duration(cfg.BuildClaimLeaseSeconds)*time.Second {
		return Config{}, fmt.Errorf("CP_BUILD_CLAIM_RENEW_INTERVAL_SECONDS must be less than CP_BUILD_CLAIM_LEASE_SECONDS")
	}
	if cfg.BuildMaxDuration >= time.Duration(cfg.BuildClaimLeaseSeconds)*time.Second {
		return Config{}, fmt.Errorf("CP_BUILD_MAX_DURATION_SECONDS must be less than CP_BUILD_CLAIM_LEASE_SECONDS")
	}
	if cfg.PullVisibilityTimeoutMS < cfg.BuildClaimLeaseSeconds*1000 {
		return Config{}, fmt.Errorf("CP_CLOUDFLARE_PULL_VISIBILITY_TIMEOUT_MS must be >= CP_BUILD_CLAIM_LEASE_SECONDS * 1000")
	}
	if cfg.BuildDockerPidsLimit < 1 {
		return Config{}, fmt.Errorf("CP_BUILD_DOCKER_PIDS_LIMIT must be >= 1")
	}
	if cfg.FetchDockerPidsLimit < 1 {
		return Config{}, fmt.Errorf("CP_FETCH_DOCKER_PIDS_LIMIT must be >= 1")
	}
	fetchCPUs, err := strconv.ParseFloat(cfg.FetchDockerCPUs, 64)
	if err != nil || fetchCPUs <= 0 {
		return Config{}, fmt.Errorf("CP_FETCH_DOCKER_CPUS must be a positive number")
	}
	cpus, err := strconv.ParseFloat(cfg.BuildDockerCPUs, 64)
	if err != nil || cpus <= 0 {
		return Config{}, fmt.Errorf("CP_BUILD_DOCKER_CPUS must be a positive number")
	}
	if cfg.FetchDockerCPUs == "" || cfg.FetchDockerMemory == "" {
		return Config{}, fmt.Errorf("CP_FETCH_DOCKER_CPUS and CP_FETCH_DOCKER_MEMORY are required")
	}
	if cfg.BuildDockerCPUs == "" || cfg.BuildDockerMemory == "" {
		return Config{}, fmt.Errorf("CP_BUILD_DOCKER_CPUS and CP_BUILD_DOCKER_MEMORY are required")
	}
	if len(cfg.AllowedDockerImages) > 0 {
		if cfg.CommandRunnerProvider == "docker" && !slices.Contains(cfg.AllowedDockerImages, cfg.BuildDockerImage) {
			return Config{}, fmt.Errorf("CP_BUILD_DOCKER_IMAGE must be present in CP_BUILD_DOCKER_ALLOWED_IMAGES")
		}
		if cfg.SourceFetcherProvider == "docker" && !slices.Contains(cfg.AllowedDockerImages, cfg.FetchDockerImage) {
			return Config{}, fmt.Errorf("CP_FETCH_DOCKER_IMAGE must be present in CP_BUILD_DOCKER_ALLOWED_IMAGES")
		}
	}

	return cfg, nil
}

func envOrDefault(key string, defaultValue string) string {
	value := os.Getenv(key)
	if value == "" {
		return defaultValue
	}
	return value
}

func intEnv(key string, defaultValue int) int {
	value := os.Getenv(key)
	if value == "" {
		return defaultValue
	}

	parsed, err := strconv.Atoi(value)
	if err != nil {
		return defaultValue
	}
	return parsed
}

func boolEnv(key string, defaultValue bool) bool {
	value := os.Getenv(key)
	if value == "" {
		return defaultValue
	}

	parsed, err := strconv.ParseBool(value)
	if err != nil {
		return defaultValue
	}
	return parsed
}

func csvEnv(key string, defaultValue []string) []string {
	value := os.Getenv(key)
	if value == "" {
		return defaultValue
	}

	parts := strings.Split(value, ",")
	result := make([]string, 0, len(parts))
	for _, part := range parts {
		trimmed := strings.TrimSpace(part)
		if trimmed == "" {
			continue
		}
		result = append(result, trimmed)
	}
	if len(result) == 0 {
		return defaultValue
	}
	return result
}
