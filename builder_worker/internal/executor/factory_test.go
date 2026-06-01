package executor

import (
	"strings"
	"testing"

	"builder_worker/internal/artifacts"
)

func TestBuildResolvesSimulatedExecutor(t *testing.T) {
	buildExecutor, err := Build(ProviderSimulated, FactoryConfig{
		Publisher: &stubPublisher{},
	})
	if err != nil {
		t.Fatalf("Build returned error: %v", err)
	}
	if _, ok := buildExecutor.(*SimulatedBuildExecutor); !ok {
		t.Fatalf("expected simulated executor, got %T", buildExecutor)
	}
}

func TestBuildResolvesActualExecutor(t *testing.T) {
	buildExecutor, err := Build(ProviderActual, FactoryConfig{
		Publisher:             &stubPublisher{},
		SourceFetcherProvider: SourceFetcherProviderHost,
		CommandRunnerProvider: CommandRunnerProviderShell,
	})
	if err != nil {
		t.Fatalf("Build returned error: %v", err)
	}
	if _, ok := buildExecutor.(*ActualBuildExecutor); !ok {
		t.Fatalf("expected actual executor, got %T", buildExecutor)
	}
}

func TestBuildRejectsUnknownProvider(t *testing.T) {
	_, err := Build("unknown", FactoryConfig{
		Publisher: &stubPublisher{},
	})
	if err == nil || !strings.Contains(err.Error(), "unsupported build executor provider") {
		t.Fatalf("expected unsupported provider error, got %v", err)
	}
}

func TestBuildRejectsUnknownCommandRunnerProvider(t *testing.T) {
	_, err := Build(ProviderActual, FactoryConfig{
		Publisher:             &stubPublisher{},
		SourceFetcherProvider: SourceFetcherProviderHost,
		CommandRunnerProvider: "unknown",
	})
	if err == nil || !strings.Contains(err.Error(), "unsupported command runner provider") {
		t.Fatalf("expected unsupported command runner provider error, got %v", err)
	}
}

func TestBuildRejectsUnknownSourceFetcherProvider(t *testing.T) {
	_, err := Build(ProviderActual, FactoryConfig{
		Publisher:             &stubPublisher{},
		SourceFetcherProvider: "unknown",
		CommandRunnerProvider: CommandRunnerProviderShell,
	})
	if err == nil || !strings.Contains(err.Error(), "unsupported source fetcher provider") {
		t.Fatalf("expected unsupported source fetcher provider error, got %v", err)
	}
}

var _ artifacts.Publisher = (*stubPublisher)(nil)
