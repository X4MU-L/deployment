package logger

import (
	"fmt"
	"os"
	"strings"
	"sync"
	"time"
)

type Level int

const (
	LevelDebug Level = iota
	LevelInfo
	LevelWarn
	LevelError
)

type Config struct {
	Level     string
	ColorMode string
}

type Literal string

type Logger struct {
	mu         sync.Mutex
	level      Level
	colorMode  string
	colorize   bool
	timeFormat string
}

var std = newLogger()

func newLogger() *Logger {
	return &Logger{
		level:      LevelInfo,
		colorMode:  "auto",
		colorize:   shouldColorize("auto"),
		timeFormat: "2006-01-02 15:04:05",
	}
}

func Init(config Config) {
	std.mu.Lock()
	defer std.mu.Unlock()

	std.level = parseLevel(config.Level)
	std.colorMode = normalizeColorMode(config.ColorMode)
	std.colorize = shouldColorize(std.colorMode)
}

func Debug(message string, kv ...any) {
	std.log(LevelDebug, message, kv...)
}

func Info(message string, kv ...any) {
	std.log(LevelInfo, message, kv...)
}

func Warn(message string, kv ...any) {
	std.log(LevelWarn, message, kv...)
}

func Error(message string, kv ...any) {
	std.log(LevelError, message, kv...)
}

func (l *Logger) log(level Level, message string, kv ...any) {
	l.mu.Lock()
	defer l.mu.Unlock()

	if level < l.level {
		return
	}

	levelLabel := level.String()
	if l.colorize {
		levelLabel = colorizeLevel(level, levelLabel)
	}

	var builder strings.Builder
	builder.WriteString(time.Now().Format(l.timeFormat))
	builder.WriteString(" ")
	builder.WriteString(levelLabel)
	builder.WriteString(" ")
	builder.WriteString(message)

	for i := 0; i < len(kv); i += 2 {
		builder.WriteString(" ")
		key := fmt.Sprint(kv[i])
		builder.WriteString(key)
		builder.WriteString("=")
		if i+1 >= len(kv) {
			builder.WriteString("<missing>")
			continue
		}
		builder.WriteString(formatValue(kv[i+1]))
	}

	fmt.Fprintln(os.Stdout, builder.String())
}

func (l Level) String() string {
	switch l {
	case LevelDebug:
		return "DEBUG"
	case LevelInfo:
		return "INFO "
	case LevelWarn:
		return "WARN "
	case LevelError:
		return "ERROR"
	default:
		return "INFO "
	}
}

func parseLevel(value string) Level {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "debug":
		return LevelDebug
	case "warn", "warning":
		return LevelWarn
	case "error":
		return LevelError
	default:
		return LevelInfo
	}
}

func normalizeColorMode(value string) string {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "always", "never":
		return strings.ToLower(strings.TrimSpace(value))
	default:
		return "auto"
	}
}

func shouldColorize(colorMode string) bool {
	switch colorMode {
	case "always":
		return true
	case "never":
		return false
	default:
		return os.Getenv("NO_COLOR") == "" && os.Getenv("TERM") != "" && os.Getenv("TERM") != "dumb"
	}
}

func colorizeLevel(level Level, label string) string {
	switch level {
	case LevelDebug:
		return "\033[36m" + label + "\033[0m"
	case LevelInfo:
		return "\033[32m" + label + "\033[0m"
	case LevelWarn:
		return "\033[33m" + label + "\033[0m"
	case LevelError:
		return "\033[31m" + label + "\033[0m"
	default:
		return label
	}
}

func formatValue(value any) string {
	switch typed := value.(type) {
	case Literal:
		return string(typed)
	case string:
		if typed == "" {
			return `""`
		}
		if strings.ContainsAny(typed, " \t\n\r") {
			return fmt.Sprintf("%q", typed)
		}
		return typed
	case error:
		return typed.Error()
	default:
		return fmt.Sprint(value)
	}
}
