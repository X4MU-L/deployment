package consumer

import (
	"context"
	"errors"
	"fmt"

	"builder_worker/internal/contracts"
	"builder_worker/internal/queue"
)

type Config struct {
	BatchSize           int
	VisibilityTimeoutMS int
	MaxAttempts         int
}

type MessageHandler interface {
	Handle(context.Context, contracts.BuildRequestedMessage) error
}

type Consumer struct {
	config      Config
	queueClient queue.Client
	handler     MessageHandler
}

func New(config Config, queueClient queue.Client, handler MessageHandler) *Consumer {
	return &Consumer{
		config:      config,
		queueClient: queueClient,
		handler:     handler,
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

	acks := make([]string, 0, len(messages))
	retries := make([]string, 0, len(messages))
	for _, message := range messages {
		action := c.classifyMessage(ctx, message)
		switch action {
		case acknowledgeMessage:
			acks = append(acks, message.LeaseID)
		case retryMessage:
			retries = append(retries, message.LeaseID)
		default:
			return 0, fmt.Errorf("unsupported queue action: %s", action)
		}
	}

	if err := c.queueClient.Acknowledge(ctx, acks, retries); err != nil {
		return 0, err
	}
	return len(messages), nil
}

type messageAction string

const (
	acknowledgeMessage messageAction = "ack"
	retryMessage       messageAction = "retry"
)

func (c *Consumer) classifyMessage(ctx context.Context, message queue.PulledMessage) messageAction {
	var buildRequest contracts.BuildRequestedMessage
	if err := message.DecodeJSON(&buildRequest); err != nil {
		return acknowledgeMessage
	}
	if err := buildRequest.Validate(); err != nil {
		return acknowledgeMessage
	}
	if err := c.handler.Handle(ctx, buildRequest); err != nil {
		if message.Attempts >= c.config.MaxAttempts || errors.Is(err, ErrTerminalHandlerFailure) {
			return acknowledgeMessage
		}
		return retryMessage
	}
	return acknowledgeMessage
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
