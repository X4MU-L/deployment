package executor

import (
	"fmt"
	"slices"
)

const (
	CommandRunnerProviderShell  = "shell"
	CommandRunnerProviderDocker = "docker"
)

type CommandRunnerFactoryConfig struct {
	DockerImage          string
	DockerInstallNetwork string
	DockerBuildNetwork   string
	DockerCPUs           string
	DockerMemory         string
	DockerMemorySwap     string
	DockerPidsLimit      int
	AllowedDockerImages  []string
}

// BuildCommandRunner is a factory function that creates a CommandRunner based on the provided provider string and configuration.
// It supports different providers, such as a shell command runner that executes commands directly on the host, and a docker command runner that executes commands inside a docker container.
// The factory function abstracts away the initialization logic for the different command runners, allowing the caller to simply specify which one they want to use.
func BuildCommandRunner(provider string, config CommandRunnerFactoryConfig) (CommandRunner, error) {
	switch provider {
	case "", CommandRunnerProviderDocker:
		if err := validateAllowedDockerImage(config.DockerImage, config.AllowedDockerImages); err != nil {
			return nil, err
		}
		return NewDockerCommandRunnerWithConfig(DockerRunnerConfig{
			Image:            config.DockerImage,
			InstallNetwork:   config.DockerInstallNetwork,
			BuildNetwork:     config.DockerBuildNetwork,
			CPUs:             config.DockerCPUs,
			Memory:           config.DockerMemory,
			MemorySwap:       config.DockerMemorySwap,
			ReadOnlyRootFS:   true,
			PidsLimit:        config.DockerPidsLimit,
			DropCapabilities: true,
			NoNewPrivileges:  true,
			MapHostUser:      true,
		}), nil
	case CommandRunnerProviderShell:
		return NewShellCommandRunner(), nil
	default:
		return nil, fmt.Errorf("unsupported command runner provider %q", provider)
	}
}

func validateAllowedDockerImage(image string, allowedImages []string) error {
	if len(allowedImages) > 0 && !slices.Contains(allowedImages, image) {
		return fmt.Errorf("docker image %q is not in the allowed image list", image)
	}
	return nil
}
