---
description: "Make an Ansible infra change (role/playbook/template/vars) with vault-safe secret handling and idempotent tasks."
name: "Edit Ansible Role/Playbook"
argument-hint: "Which role/playbook? What should change?"
agent: "Infra (Ansible)"
---
Apply the requested infra change in the Ansible repo.

Target repo in this workspace: `ngrok_alternative/infra/`.

Constraints:
- Do not run playbooks unless explicitly asked.
- Never introduce plaintext secrets; use encrypted vault files.
- Keep tasks idempotent; prefer modules + templates + handlers.

Deliverables:
- Updated role/playbook/template/vars
- Risk notes (service restarts, downtime)
- Safe validation suggestions (syntax-check / check mode)
