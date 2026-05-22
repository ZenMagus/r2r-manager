# Sync Policy

## Default mode

Dry-run only.

## Apply mode

R2R writes require explicit `--apply`.

## Delete/stale policy

Missing local docs should not be deleted from R2R by default.

Preferred initial behavior:

- report stale docs
- mark stale/inactive only if R2R supports it and user approves
- delete only with explicit `--delete-stale --apply`

## Canonical docs

Project manifests decide what gets indexed. Do not blindly ingest every file under `docs/`.

## Metadata

Every ingested document should include Git metadata and content hash so R2R can be rebuilt or scrubbed later.
