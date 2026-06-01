package main

import (
	"context"
	"errors"
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"

	"builder_worker/internal/config"
	"builder_worker/internal/consumer"
	"builder_worker/internal/handler"
	"builder_worker/internal/logger"
	"builder_worker/internal/queue"
)

func main() {
	// load configuration from environment variables
	// We configure a couple of things in the config, like cloudflare credentials
	// internal tokens, etc. that we don't want to pass as command line arguments
	cfg, err := config.LoadFromEnv()
	if err != nil {
		fmt.Fprintf(os.Stderr, "load config: %v\n", err)
		os.Exit(1)
	}
	logger.Init(logger.Config{
		Level:     cfg.LogLevel,
		ColorMode: cfg.LogColor,
	})
	logger.Info(
		"builder worker configuration loaded",
		"build_executor_provider",
		cfg.BuildExecutorProvider,
		"artifact_store_provider",
		cfg.ArtifactStoreProvider,
		"command_runner_provider",
		cfg.CommandRunnerProvider,
		"r2_endpoint_url",
		cfg.R2EndpointURL,
		"cloudflare_queue_id",
		cfg.CloudflareQueueID,
		"log_level",
		cfg.LogLevel,
		"log_color",
		cfg.LogColor,
		"run_once",
		cfg.RunOnce,
	)

	// set up signal handling for graceful shutdown
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	// Initialize Queue client
	// The queue client uses the aws-sdk-go-v2 which does not support context cancellation on long polling ReceiveMessage calls.
	// To ensure we can gracefully shut down, we set the long poll wait time to a value shorter than our shutdown timeout and rely on context cancellation between calls.
	// the queue client implements interfaces to
	// Pull messages from the queue and delete them when done, but does not handle visibility timeouts or retries, which are handled by the consumer.
	// Acknowlegde messages..
	queueClient := queue.NewHTTPClient(queue.Config{
		APIBaseURL: cfg.CloudflareAPIBaseURL,
		AccountID:  cfg.CloudflareAccountID,
		APIToken:   cfg.CloudflareAPIToken,
		QueueID:    cfg.CloudflareQueueID,
	})

	// Initialize Build Handler
	// The build handler is responsible for processing build messages pulled from the queue, executing the builds using the configured executor, and reporting results back to the control plane.
	// The bulder will send logs back to the control plane in real time, and will report the final build status (success/failure) along with any error messages.
	// Here is how the Factory/Adaptor pattern is resolved
	// The NewBuildHandler function takes in the configuration and initializes the appropriate build executor, publisher, control plane client to report back logs and results, etc. based on the configuration.
	// and a log forwarder to forward logs from the build executor to the control plane in real time.
	// the builder handler exposes a single Handle method.
	// The cunsumer will call the Handle method for each message pulled from the queue, and the handler will take care of executing the build and reporting results.
	// TThe Handle method, gets the build from control plane, using the control plane client
	// updates it's status to "running" and creates a channel to pass logs from the executor back to the control plane.
	// Then it calls the Execute method on the build executor, passing in the build and the log channel.
	// The build executor will execute the build, sending logs back through the channel, and return a final result when done.
	// The handler will then take that result and report it back to the control plane, updating the build status to "success" or "failure" accordingly.
	buildHandler, err := handler.NewBuildHandler(handler.BuildHandlerConfig{
		ControlPlaneBaseURL:   cfg.ControlPlaneBaseURL,
		ServiceToken:          cfg.InternalServiceToken,
		ServiceName:           cfg.ServiceName,
		ClaimLeaseSeconds:     cfg.BuildClaimLeaseSeconds,
		ClaimRenewInterval:    cfg.BuildClaimRenewInterval,
		BuildMaxDuration:      cfg.BuildMaxDuration,
		BuildExecutorProvider: cfg.BuildExecutorProvider,
		SourceFetcherProvider: cfg.SourceFetcherProvider,
		FetchDockerImage:      cfg.FetchDockerImage,
		FetchDockerNetwork:    cfg.FetchDockerNetwork,
		FetchDockerCPUs:       cfg.FetchDockerCPUs,
		FetchDockerMemory:     cfg.FetchDockerMemory,
		FetchDockerMemorySwap: cfg.FetchDockerMemorySwap,
		FetchDockerPidsLimit:  cfg.FetchDockerPidsLimit,
		CommandRunnerProvider: cfg.CommandRunnerProvider,
		BuildDockerImage:      cfg.BuildDockerImage,
		BuildDockerInstallNet: cfg.BuildDockerInstallNet,
		BuildDockerBuildNet:   cfg.BuildDockerBuildNet,
		BuildDockerCPUs:       cfg.BuildDockerCPUs,
		BuildDockerMemory:     cfg.BuildDockerMemory,
		BuildDockerMemorySwap: cfg.BuildDockerMemorySwap,
		BuildDockerPidsLimit:  cfg.BuildDockerPidsLimit,
		AllowedDockerImages:   cfg.AllowedDockerImages,
		ArtifactStoreProvider: cfg.ArtifactStoreProvider,
		ArtifactStoreRoot:     cfg.ArtifactStoreRoot,
		R2EndpointURL:         cfg.R2EndpointURL,
		R2AccessKeyID:         cfg.R2AccessKeyID,
		R2SecretAccessKey:     cfg.R2SecretAccessKey,
		R2SessionToken:        cfg.R2SessionToken,
		R2Region:              cfg.R2Region,
	})
	if err != nil {
		logger.Error("build handler initialization failed", "err", err)
		os.Exit(1)
	}

	// Initialize and start the consumer loop
	// The consumer continuously polls the queue for new build messages and hands each pulled batch to a bounded-concurrency job hub.
	// That hub invokes the build handler in parallel up to the configured limit, while the consumer still owns the final ack/retry decision for each lease.
	// This keeps queue outcome coupled to actual build completion instead of fire-and-forget dispatch, but avoids serializing an entire batch behind one long-running build.
	pullConsumer := consumer.New(consumer.Config{
		BatchSize:           cfg.PullBatchSize,
		VisibilityTimeoutMS: cfg.PullVisibilityTimeoutMS,
		MaxAttempts:         cfg.PullMaxAttempts,
		MaxConcurrentBuilds: cfg.PullMaxConcurrentBuilds,
	}, queueClient, buildHandler)

	if cfg.RunOnce {
		if _, err := pullConsumer.RunOnce(ctx); err != nil {
			logger.Error("builder worker run once failed", "err", err)
			os.Exit(1)
		}
		return
	}

	ticker := time.NewTicker(cfg.PullPollInterval)
	defer ticker.Stop()

	for {
		processed, err := pullConsumer.RunOnce(ctx)
		if err != nil && !errors.Is(err, context.Canceled) {
			logger.Error("consumer cycle failed", "err", err)
		}

		if processed == 0 {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
			}
			continue
		}

		select {
		case <-ctx.Done():
			return
		default:
		}
	}
}
