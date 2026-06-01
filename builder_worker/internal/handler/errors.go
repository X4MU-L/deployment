package handler

import (
	"fmt"

	"builder_worker/internal/consumer"
)

func TerminalError(err error) error {
	if err == nil {
		return consumer.TerminalError(fmt.Errorf("terminal build handler error"))
	}
	return consumer.TerminalError(err)
}
