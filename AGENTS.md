# r2r-manager Agent Guide

Read this file before making changes.

## Scope

Work only in `/home/w/projects/zenmagus/r2r-manager` unless explicitly instructed otherwise.

The `projects/` directory contains symlinks to registered source projects. Treat them as read-only references unless a task explicitly says otherwise.

## Source of truth

Git-tracked project docs are canonical. R2R is a generated/searchable index.

## Safety rules

- Dry-run by default.
- Require explicit `--apply` before writing to R2R.
- Never delete from R2R by default.
- Use explicit `--delete-stale` or equivalent only after the user approves.
- Store Git metadata and content hashes with ingested documents.
- Do not ingest generated artifacts, datasets, secrets, venvs, caches, audio outputs, or model files.
- Do not perform R2R writes in tests.
- Mock R2R APIs in tests.

## Registered projects

- edub
- voice-stack
- autodub
- local-runtime-manager

## Future collections

- edub
- voice-stack
- autodub
- local-runtime-manager
- shared-decisions
