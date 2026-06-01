package config

import (
	"fmt"
	"os"
	"slices"
	"strconv"
	"strings"
	"time"
)

type Config struct {
	CloudflareAPIBaseURL    string
	CloudflareAccountID     string
	CloudflareAPIToken      string
	CloudflareQueueID       string
	PullBatchSize           int
	PullVisibilityTimeoutMS int
	PullPollInterval        time.Duration
	PullMaxAttempts         int
	ControlPlaneBaseURL     string
	InternalServiceToken    string
	ServiceName             string
	BuildExecutorProvider   string
	CommandRunnerProvider   string
	BuildDockerImage        string
	BuildDockerInstallNet   string
	BuildDockerBuildNet     string
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
	cfg := Config{
		CloudflareAPIBaseURL:    envOrDefault("CP_CLOUDFLARE_API_BASE_URL", "https://api.cloudflare.com/client/v4"),
		CloudflareAccountID:     os.Getenv("CP_CLOUDFLARE_ACCOUNT_ID"),
		CloudflareAPIToken:      os.Getenv("CP_CLOUDFLARE_API_TOKEN"),
		CloudflareQueueID:       os.Getenv("CP_CLOUDFLARE_QUEUE_ID"),
		PullBatchSize:           intEnv("CP_CLOUDFLARE_PULL_BATCH_SIZE", 5),
		PullVisibilityTimeoutMS: intEnv("CP_CLOUDFLARE_PULL_VISIBILITY_TIMEOUT_MS", 30000),
		PullPollInterval:        time.Duration(intEnv("CP_CLOUDFLARE_PULL_POLL_INTERVAL_SECONDS", 5)) * time.Second,
		PullMaxAttempts:         intEnv("CP_CLOUDFLARE_PULL_MAX_ATTEMPTS", 3),
		ControlPlaneBaseURL:     envOrDefault("CP_CELERY_BUILDER_BASE_URL", "http://localhost:8000"),
		InternalServiceToken:    os.Getenv("CP_INTERNAL_SERVICE_TOKEN"),
		ServiceName:             envOrDefault("CP_CELERY_BUILDER_SERVICE_NAME", "cloudflare-builder-worker"),
		BuildExecutorProvider:   envOrDefault("CP_BUILD_EXECUTOR_PROVIDER", "simulated"),
		CommandRunnerProvider:   envOrDefault("CP_BUILD_COMMAND_RUNNER_PROVIDER", "docker"),
		BuildDockerImage:        envOrDefault("CP_BUILD_DOCKER_IMAGE", "node:20-bookworm"),
		BuildDockerInstallNet:   envOrDefault("CP_BUILD_DOCKER_INSTALL_NETWORK", "bridge"),
		BuildDockerBuildNet:     envOrDefault("CP_BUILD_DOCKER_BUILD_NETWORK", "none"),
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

	if cfg.PullBatchSize < 1 {
		return Config{}, fmt.Errorf("CP_CLOUDFLARE_PULL_BATCH_SIZE must be >= 1")
	}
	if cfg.PullVisibilityTimeoutMS < 1000 {
		return Config{}, fmt.Errorf("CP_CLOUDFLARE_PULL_VISIBILITY_TIMEOUT_MS must be >= 1000")
	}
	if cfg.PullMaxAttempts < 1 {
		return Config{}, fmt.Errorf("CP_CLOUDFLARE_PULL_MAX_ATTEMPTS must be >= 1")
	}
	if cfg.BuildDockerPidsLimit < 1 {
		return Config{}, fmt.Errorf("CP_BUILD_DOCKER_PIDS_LIMIT must be >= 1")
	}
	if cfg.CommandRunnerProvider == "docker" && len(cfg.AllowedDockerImages) > 0 && !slices.Contains(cfg.AllowedDockerImages, cfg.BuildDockerImage) {
		return Config{}, fmt.Errorf("CP_BUILD_DOCKER_IMAGE must be present in CP_BUILD_DOCKER_ALLOWED_IMAGES")
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
