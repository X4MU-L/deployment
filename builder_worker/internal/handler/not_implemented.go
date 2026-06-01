package handler

import (
	"context"
	"fmt"

	"builder_worker/internal/contracts"
)

type NotImplementedConfig struct {
	ControlPlaneBaseURL string
	ServiceName         string
}

type NotImplementedHandler struct {
	config NotImplementedConfig
}

func NewNotImplementedHandler(config NotImplementedConfig) *NotImplementedHandler {
	return &NotImplementedHandler{config: config}
}

func (h *NotImplementedHandler) Handle(_ context.Context, message contracts.BuildRequestedMessage) error {
	return TerminalError(fmt.Errorf(
		"%w: build execution port is not implemented yet for build %s via %s",
		errNotImplemented,
		message.BuildID,
		h.config.ServiceName,
	))
}

var errNotImplemented = fmt.Errorf("builder handler not implemented")
