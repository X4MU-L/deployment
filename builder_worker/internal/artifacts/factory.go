package artifacts

import "fmt"

// Create a factory function for BuildExecutors based on the provider specified in the configuration.
// The factory function takes a provider string and a configuration struct, and returns an implementation of the BuildExecutor interface.
// This allows us to easily switch between different implementations of the BuildExecutor (e.g. simulated vs actual) based on configuration, without changing the code that uses the BuildExecutor.
// FactoryConfig holds the configuration for creating a BuildExecutor.
// It includes the artifact publisher, command runner provider, Docker configuration, and allowed Docker images.
func BuildPublisher(provider string, config PublisherConfig) (Publisher, error) {
	switch provider {
	case "", "local":
		return NewLocalPublisher(config.Root), nil
	case "r2":
		return NewR2Publisher(config)
	default:
		return nil, fmt.Errorf("unsupported artifact_store_provider: %s", provider)
	}
}
