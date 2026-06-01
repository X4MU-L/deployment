package consumer

import (
	"context"
	"errors"
	"sync"

	"builder_worker/internal/contracts"
	"builder_worker/internal/queue"
)

type MessageHandler interface {
	Handle(context.Context, contracts.BuildRequestedMessage) error
}

type messageAction string

const (
	acknowledgeMessage messageAction = "ack"
	retryMessage       messageAction = "retry"
)

type BuildJobHub struct {
	maxConcurrent int
	maxAttempts   int
	handler       MessageHandler
}

type jobOutcome struct {
	index  int
	action messageAction
}

func NewBuildJobHub(maxConcurrent int, maxAttempts int, handler MessageHandler) *BuildJobHub {
	if maxConcurrent < 1 {
		maxConcurrent = 1
	}
	return &BuildJobHub{
		maxConcurrent: maxConcurrent,
		maxAttempts:   maxAttempts,
		handler:       handler,
	}
}

func (h *BuildJobHub) ProcessBatch(
	ctx context.Context,
	messages []queue.PulledMessage,
) []messageAction {
	results := make([]messageAction, len(messages))
	if len(messages) == 0 {
		return results
	}

	semaphore := make(chan struct{}, h.maxConcurrent)
	outcomes := make(chan jobOutcome, len(messages))
	var waitGroup sync.WaitGroup

	for index, message := range messages {
		waitGroup.Add(1)
		semaphore <- struct{}{}
		go func(index int, message queue.PulledMessage) {
			defer waitGroup.Done()
			defer func() {
				<-semaphore
			}()
			outcomes <- jobOutcome{
				index:  index,
				action: h.classifyMessage(ctx, message),
			}
		}(index, message)
	}

	go func() {
		waitGroup.Wait()
		close(outcomes)
	}()

	for outcome := range outcomes {
		results[outcome.index] = outcome.action
	}
	return results
}

func (h *BuildJobHub) classifyMessage(ctx context.Context, message queue.PulledMessage) messageAction {
	var buildRequest contracts.BuildRequestedMessage
	if err := message.DecodeJSON(&buildRequest); err != nil {
		return acknowledgeMessage
	}
	if err := buildRequest.Validate(); err != nil {
		return acknowledgeMessage
	}
	if err := h.handler.Handle(ctx, buildRequest); err != nil {
		if message.Attempts >= h.maxAttempts || errors.Is(err, ErrTerminalHandlerFailure) {
			return acknowledgeMessage
		}
		return retryMessage
	}
	return acknowledgeMessage
}
