---
name: ansible-systemd-service-role
description: Use when creating or changing an Ansible role that deploys an application as a systemd service: defaults, vars, templates, env files, handlers, idempotent tasks, service enable/start, and syntax validation.
---

# Ansible Systemd Service Role

## Purpose

Create an idempotent Ansible role for deploying an app or worker as a managed systemd service.

Use this when:

- Deploying a Python, Go, Node, or other long-running service.
- Adding env templates and systemd units.
- Changing service restart behavior.
- Wiring deployment vars and handlers.
- Deploying origin routers, builder workers, or other platform agents behind a systemd-managed entrypoint.

## First Questions

- What binary or command starts the service?
- Where is the source/build artifact located?
- Which user/group should own files and run the service?
- Which environment values are secrets?
- Which values are shared across roles?
- What changes should trigger restart vs reload?
- Does deployment require build, dependency install, migration, or config generation?
- If Docker is involved, does systemd start the app directly or supervise a Docker-based entrypoint?

## Role Shape

```text
roles/<service>/
  defaults/main.yml
  handlers/main.yml
  tasks/main.yml
  templates/<service>.env.j2
  templates/<service>.service.j2
```

Use:

- `defaults/main.yml` for role-level overridable defaults.
- Inventory/group vars for shared paths, ports, domains, repo refs.
- Vault vars for secrets.
- Templates for env files and systemd units.
- Handlers for restarts and daemon reloads.

## Task Order

Typical `tasks/main.yml`:

1. Install runtime/build tool if missing.
2. Ensure directories exist.
3. Build or sync dependencies idempotently.
4. Write env/config templates.
5. Run migrations or one-time setup if configured.
6. Deploy systemd unit.
7. Enable and start service.

For platform services such as builders or origin routers:

- keep runtime paths and env files explicit
- separate Docker daemon concerns from the service unit when possible
- decide whether config changes require reload or full restart

Prefer modules:

- `ansible.builtin.package`
- `ansible.builtin.file`
- `ansible.builtin.template`
- `ansible.builtin.copy`
- `ansible.builtin.systemd`
- `ansible.builtin.get_url`

Use `command` only with `creates`, `changed_when`, or another idempotency guard.

## Handlers

```yaml
- name: Reload systemd
  ansible.builtin.systemd:
    daemon_reload: true

- name: Restart service
  ansible.builtin.systemd:
    name: "{{ service_name }}"
    state: restarted
```

Notify reload when unit templates change. Notify restart when env/config/runtime files change.

## Env Template

- Put generated file warnings at top.
- Reference secrets through vault variables.
- Reference non-secrets through normal vars.
- Do not hardcode environment-specific domains, keys, or ports.
- Use absolute paths for service runtime values.

## Systemd Template

Include:

- `WorkingDirectory`
- `EnvironmentFile` when using env files.
- `ExecStart`
- `Restart`
- `RestartSec`
- `User` and `Group` when applicable.
- `WantedBy=multi-user.target`

If the service fronts other infrastructure, also consider:

- `After=` and `Requires=` for Docker or network dependencies
- restart throttling that avoids tight crash loops during bad config deploys

## Validation

Run when available:

```bash
ansible-playbook --syntax-check playbooks/site.yml
ansible-lint
```

Do not run real deployment playbooks unless explicitly asked.
