package consumer

import (
	"context"
	"errors"
	"sync"
	"time"

	"builder_worker/internal/contracts"
	"builder_worker/internal/logger"
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
	message       queue.PulledMessage
	action        messageAction
	buildID       string
	projectID     string
	releaseID     string
	correlationID string
	attempt       int
	reason        string
	err           error
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
		inflight := h.inflight
		h.mu.Unlock()

		logger.Info(
			"build job accepted",
			"message_id",
			message.ID,
			"lease_id",
			message.LeaseID,
			"attempts",
			message.Attempts,
			"content_type",
			message.ContentType(),
			"inflight",
			inflight,
			"max",
			h.maxConcurrent,
		)

		go func() {
			start := time.Now()
			outcome := h.classifyMessage(ctx, message)
			h.results <- outcome
			<-h.semaphore
			h.mu.Lock()
			h.inflight--
			inflight := h.inflight
			h.mu.Unlock()

			logger.Info(
				"build job completed",
				"message_id",
				message.ID,
				"lease_id",
				message.LeaseID,
				"build_id",
				outcome.buildID,
				"correlation_id",
				outcome.correlationID,
				"action",
				outcome.action,
				"reason",
				outcome.reason,
				"duration_ms",
				time.Since(start).Milliseconds(),
				"inflight",
				inflight,
				"err",
				outcome.err,
			)
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

func (h *BuildJobHub) classifyMessage(ctx context.Context, message queue.PulledMessage) jobOutcome {
	var buildRequest contracts.BuildRequestedMessage
	if err := message.DecodeJSON(&buildRequest); err != nil {
		logger.Warn(
			"build job decode failed",
			"message_id",
			message.ID,
			"lease_id",
			message.LeaseID,
			"content_type",
			message.ContentType(),
			"err",
			err,
		)
		return jobOutcome{
			message: message,
			action:  acknowledgeMessage,
			reason:  "decode_failed",
			err:     err,
		}
	}
	outcome := jobOutcome{
		message:       message,
		buildID:       buildRequest.BuildID,
		projectID:     buildRequest.ProjectID,
		releaseID:     buildRequest.ReleaseID,
		correlationID: buildRequest.CorrelationID,
		attempt:       buildRequest.Attempt,
	}
	if err := buildRequest.Validate(); err != nil {
		logger.Warn(
			"build job validation failed",
			"message_id",
			message.ID,
			"lease_id",
			message.LeaseID,
			"build_id",
			buildRequest.BuildID,
			"correlation_id",
			buildRequest.CorrelationID,
			"err",
			err,
		)
		outcome.action = acknowledgeMessage
		outcome.reason = "validation_failed"
		outcome.err = err
		return outcome
	}
	logger.Debug(
		"build job decoded",
		"message_id",
		message.ID,
		"lease_id",
		message.LeaseID,
		"build_id",
		buildRequest.BuildID,
		"project_id",
		buildRequest.ProjectID,
		"release_id",
		buildRequest.ReleaseID,
		"correlation_id",
		buildRequest.CorrelationID,
		"attempt",
		buildRequest.Attempt,
	)
	if err := h.handler.Handle(ctx, buildRequest); err != nil {
		if message.Attempts >= h.maxAttempts || errors.Is(err, ErrTerminalHandlerFailure) {
			outcome.action = acknowledgeMessage
			outcome.err = err
			if message.Attempts >= h.maxAttempts {
				outcome.reason = "max_attempts_reached"
				logger.Warn(
					"build job handler failed permanently",
					"build_id",
					buildRequest.BuildID,
					"correlation_id",
					buildRequest.CorrelationID,
					"attempts",
					message.Attempts,
					"max_attempts",
					h.maxAttempts,
					"err",
					err,
				)
				return outcome
			}
			outcome.reason = "terminal_handler_error"
			logger.Warn(
				"build job handler returned terminal error",
				"build_id",
				buildRequest.BuildID,
				"correlation_id",
				buildRequest.CorrelationID,
				"err",
				err,
			)
			return outcome
		}
		outcome.action = retryMessage
		outcome.reason = "transient_handler_error"
		outcome.err = err
		logger.Warn(
			"build job handler failed and will retry",
			"build_id",
			buildRequest.BuildID,
			"correlation_id",
			buildRequest.CorrelationID,
			"attempts",
			message.Attempts,
			"max_attempts",
			h.maxAttempts,
			"err",
			err,
		)
		return outcome
	}
	logger.Info(
		"build job processed successfully",
		"build_id",
		buildRequest.BuildID,
		"project_id",
		buildRequest.ProjectID,
		"release_id",
		buildRequest.ReleaseID,
		"correlation_id",
		buildRequest.CorrelationID,
	)
	outcome.action = acknowledgeMessage
	outcome.reason = "handled"
	return outcome
}
