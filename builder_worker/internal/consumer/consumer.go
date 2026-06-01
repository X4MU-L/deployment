package consumer

import (
	"context"

	"builder_worker/internal/queue"
)

type Config struct {
	BatchSize           int
	VisibilityTimeoutMS int
	MaxAttempts         int
	MaxConcurrentBuilds int
}

type Consumer struct {
	config      Config
	queueClient queue.Client
	jobHub      *BuildJobHub
}

func New(config Config, queueClient queue.Client, handler MessageHandler) *Consumer {
	return &Consumer{
		config:      config,
		queueClient: queueClient,
		jobHub:      NewBuildJobHub(config.MaxConcurrentBuilds, config.MaxAttempts, handler),
	}
}

func (c *Consumer) RunOnce(ctx context.Context) (int, error) {
	messages, err := c.queueClient.PullMessages(ctx, c.config.BatchSize, c.config.VisibilityTimeoutMS)
	if err != nil {
		return 0, err
	}
	if len(messages) == 0 {
		return 0, nil
	}

	actions := c.jobHub.ProcessBatch(ctx, messages)
	acks := make([]string, 0, len(messages))
	retries := make([]string, 0, len(messages))
	for index, message := range messages {
		action := actions[index]
		switch action {
		case acknowledgeMessage:
			acks = append(acks, message.LeaseID)
		case retryMessage:
			retries = append(retries, message.LeaseID)
		}
	}

	if err := c.queueClient.Acknowledge(ctx, acks, retries); err != nil {
		return 0, err
	}
	return len(messages), nil
}

var ErrTerminalHandlerFailure = errors.New("terminal handler failure")

func TerminalError(err error) error {
	if err == nil {
		return ErrTerminalHandlerFailure
	}
	return fmt.Errorf("%w: %v", ErrTerminalHandlerFailure, err)
}

func IsTerminalError(err error) bool {
	return errors.Is(err, ErrTerminalHandlerFailure)
}
