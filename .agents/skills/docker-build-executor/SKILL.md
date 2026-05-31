---
name: docker-build-executor
description: Use when implementing or changing the isolated build executor for static app builds, including ephemeral Docker workspaces, checkout/build command execution, ordered log capture, artifact packaging, manifest generation, and secret-boundary handling.
---

# Docker Build Executor

## Purpose

Turn a source checkout into an immutable static release safely enough for the first product.

Use this when:

- implementing the builder's execution path
- adding Docker-isolated build steps
- packaging release artifacts and manifest output
- defining what build-time secrets are allowed

## Minimal Execution Flow

1. create an ephemeral workspace
2. checkout the requested commit
3. run install/build commands in Docker
4. capture stdout/stderr in order
5. collect the declared output directory
6. hash files and generate `static_release_manifest.v1`
7. upload artifacts and report completion

## Isolation Rules

- do not expose the host Docker socket to untrusted build containers
- keep workspaces ephemeral
- avoid mounting sensitive host paths
- treat user build commands as untrusted input

## Artifact Rules

- release paths are immutable
- manifest generation is part of success, not an optional extra
- hashed assets should be separated from HTML in cache policy thinking

## Tests

Cover:

- successful build output packaging
- missing output directory
- failed install/build command
- manifest generation
- secret filtering or absence where applicable
