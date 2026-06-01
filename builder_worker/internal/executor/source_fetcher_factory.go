package executor

import "fmt"

const (
	SourceFetcherProviderHost   = "host"
	SourceFetcherProviderDocker = "docker"
)

type SourceFetcherFactoryConfig struct {
	DockerImage         string
	DockerNetwork       string
	DockerCPUs          string
	DockerMemory        string
	DockerMemorySwap    string
	DockerPidsLimit     int
	AllowedDockerImages []string
}

func BuildSourceFetcher(provider string, config SourceFetcherFactoryConfig) (SourceFetcher, error) {
	switch provider {
	case "", SourceFetcherProviderDocker:
		if err := validateAllowedDockerImage(config.DockerImage, config.AllowedDockerImages); err != nil {
			return nil, err
		}
		return NewDockerGitSourceFetcherWithConfig(DockerGitSourceFetcherConfig{
			Image:            config.DockerImage,
			NetworkMode:      config.DockerNetwork,
			CPUs:             config.DockerCPUs,
			Memory:           config.DockerMemory,
			MemorySwap:       config.DockerMemorySwap,
			PidsLimit:        config.DockerPidsLimit,
			DropCapabilities: true,
			NoNewPrivileges:  true,
			MapHostUser:      true,
		}), nil
	case SourceFetcherProviderHost:
		return &GitSourceFetcher{}, nil
	default:
		return nil, fmt.Errorf("unsupported source fetcher provider %q", provider)
	}
}
