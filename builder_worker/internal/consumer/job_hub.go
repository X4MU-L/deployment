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
	semaphore     chan struct{}
	results       chan jobOutcome
	mu            sync.Mutex
	inflight      int
}

type jobOutcome struct {
	message queue.PulledMessage
	action  messageAction
}

func NewBuildJobHub(maxConcurrent int, maxAttempts int, handler MessageHandler) *BuildJobHub {
	if maxConcurrent < 1 {
		maxConcurrent = 1
	}
	return &BuildJobHub{
		maxConcurrent: maxConcurrent,
		maxAttempts:   maxAttempts,
		handler:       handler,
		semaphore:     make(chan struct{}, maxConcurrent),
		results:       make(chan jobOutcome, maxConcurrent),
	}
}

func (h *BuildJobHub) InFlight() int {
	h.mu.Lock()
	defer h.mu.Unlock()
	return h.inflight
}

func (h *BuildJobHub) AvailableCapacity() int {
	return h.maxConcurrent - h.InFlight()
}

func (h *BuildJobHub) TrySubmit(ctx context.Context, message queue.PulledMessage) bool {
	select {
	case h.semaphore <- struct{}{}:
		h.mu.Lock()
		h.inflight++
		h.mu.Unlock()

		go func() {
			action := h.classifyMessage(ctx, message)
			h.results <- jobOutcome{
				message: message,
				action:  action,
			}
			<-h.semaphore
			h.mu.Lock()
			h.inflight--
			h.mu.Unlock()
		}()
		return true
	default:
		return false
	}
}

func (h *BuildJobHub) DrainReadyResults() []jobOutcome {
	outcomes := make([]jobOutcome, 0)
	for {
		select {
		case outcome := <-h.results:
			outcomes = append(outcomes, outcome)
		default:
			return outcomes
		}
	}
}

func (h *BuildJobHub) WaitForResult(ctx context.Context) (jobOutcome, bool) {
	select {
	case <-ctx.Done():
		return jobOutcome{}, false
	case outcome := <-h.results:
		return outcome, true
	}
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
