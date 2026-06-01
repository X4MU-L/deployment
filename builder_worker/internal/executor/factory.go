package executor

import (
	"fmt"

	"builder_worker/internal/artifacts"
)

const (
	ProviderSimulated = "simulated"
	ProviderActual    = "actual"
)

type FactoryConfig struct {
	Publisher             artifacts.Publisher
	CommandRunnerProvider string
	DockerImage           string
	DockerInstallNetwork  string
	DockerBuildNetwork    string
	DockerPidsLimit       int
	AllowedDockerImages   []string
}

// Build is a factory function that creates a BuildExecutor based on the provided provider string and configuration.
// It supports different providers, such as a simulated build executor for testing and an actual build executor that runs real builds.
// The factory function abstracts away the initialization logic for the different build executors, allowing the caller to simply specify which one they want to use.
func Build(provider string, config FactoryConfig) (BuildExecutor, error) {
	switch provider {
	case "", ProviderSimulated:
		return NewSimulatedBuildExecutor(config.Publisher), nil
	case ProviderActual:
		runner, err := BuildCommandRunner(config.CommandRunnerProvider, CommandRunnerFactoryConfig{
			DockerImage:          config.DockerImage,
			DockerInstallNetwork: config.DockerInstallNetwork,
			DockerBuildNetwork:   config.DockerBuildNetwork,
			DockerPidsLimit:      config.DockerPidsLimit,
			AllowedDockerImages:  config.AllowedDockerImages,
		})
		if err != nil {
			return nil, err
		}
		return NewActualBuildExecutorWithDeps(config.Publisher, &GitSourceFetcher{}, runner), nil
	default:
		return nil, fmt.Errorf("unsupported build executor provider %q", provider)
	}
}
