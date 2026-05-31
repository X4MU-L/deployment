---
name: go-cli-command-slice
description: Use when adding or changing a Go CLI command with clean parsing, typed command structs, dependency-injected command execution, readable user errors, telemetry/logging separation, and tests.
---

# Go CLI Command Slice

## Purpose

Add a CLI command while keeping parsing, dispatch, and execution separate.

Use this when:

- Adding a subcommand.
- Adding flags or positional arguments.
- Adding command orchestration around an API client or service.
- Improving command output or error handling.

## First Questions

- Is this a new command or a flag on an existing command?
- What is parsed from CLI input?
- What service/client does the command need?
- Does it require local config or authentication?
- Is it short-lived or long-running?
- How does it handle interrupt/shutdown?
- What output is intended for humans vs scripts?

## Project Shape

Use or adapt this structure:

```text
cmd/<binary>/main.go        # dependency wiring and dispatch only
internal/cmdparse/          # flags, args, parsed command structs
internal/commands/          # command execution
internal/config/            # local config/auth
internal/telemetry/         # logging and API/user error formatting
internal/<domain>/          # business orchestration services
```

## Parser Pattern

- Define typed parsed structs.
- Use `flag.NewFlagSet(name, flag.ContinueOnError)` or the project’s parser library.
- Validate enum values, ports, paths, and required args in the parser.
- Normalize values such as protocol or mode.
- Support positional arguments only when they improve UX and are tested.
- Add tests for defaults, aliases, invalid values, and mixed positional/flag forms.

## Command Execution Pattern

Command functions receive dependencies and parsed input:

```go
func RunDeploy(svc *deploy.Service, parsed cmdparse.Deploy) error {
    cfg, err := config.Load()
    if err != nil {
        return fmt.Errorf("load config: %w", err)
    }
    return svc.Run(parsed.Target, cfg.Token)
}
```

Rules:

- Do not parse flags in command execution.
- Do not construct low-level clients in command execution if `main` can inject them.
- Return errors to central error handling.
- Keep user-facing errors readable.
- Send verbose details to telemetry/logging.

## Long-Running Commands

For commands that keep a process alive:

- Use `signal.NotifyContext`.
- Defer remote cleanup immediately after successful setup.
- Ensure goroutines stop on context cancellation.
- Handle normal cancellation differently from real failures.
- Keep interactive UI optional and disabled when stdin/stdout are not terminals.

## Main Dispatch

`main` should:

- Parse args.
- Configure telemetry/version.
- Construct clients/services.
- Switch on parsed command name.
- Call command function.
- Convert errors to exit code.

It should not contain business workflows.

## Tests

Add:

- Parser tests.
- Command tests with fake services/clients.
- API error formatting tests when applicable.
- Interrupt/cleanup tests for long-running commands when practical.

Run:

```bash
go test ./...
gofmt -w <changed-go-files>
```
