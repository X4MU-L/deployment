package consumer

import (
	"context"
	"errors"
	"fmt"

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
	activity := 0
	acks := make([]string, 0)
	retries := make([]string, 0)

	collectOutcome := func(outcome jobOutcome) {
		switch outcome.action {
		case acknowledgeMessage:
			acks = append(acks, outcome.message.LeaseID)
		case retryMessage:
			retries = append(retries, outcome.message.LeaseID)
		}
		activity++
	}

	for _, outcome := range c.jobHub.DrainReadyResults() {
		collectOutcome(outcome)
	}

	availableCapacity := min(c.config.BatchSize, c.jobHub.AvailableCapacity())
	if availableCapacity > 0 {
		messages, err := c.queueClient.PullMessages(ctx, availableCapacity, c.config.VisibilityTimeoutMS)
		if err != nil {
			return 0, err
		}
		for _, message := range messages {
			if !c.jobHub.TrySubmit(ctx, message) {
				break
			}
			activity++
		}
		for _, outcome := range c.jobHub.DrainReadyResults() {
			collectOutcome(outcome)
		}
	}

	if activity == 0 && c.jobHub.InFlight() > 0 {
		outcome, ok := c.jobHub.WaitForResult(ctx)
		if !ok {
			return 0, ctx.Err()
		}
		collectOutcome(outcome)
		for _, additional := range c.jobHub.DrainReadyResults() {
			collectOutcome(additional)
		}
	}

	if len(acks)+len(retries) > 0 {
		if err := c.queueClient.Acknowledge(ctx, acks, retries); err != nil {
			return 0, err
		}
	}
	return activity, nil
}

func (c *Consumer) InFlight() int {
	return c.jobHub.InFlight()
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
