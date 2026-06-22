# Sync Policy

## Default mode

Dry-run only.

`plan_sync.py` only plans local candidates. It reports `would_update_unknown` for readable docs because it intentionally does not call R2R.

`compare_r2r.py` performs live read-only comparison against R2R document metadata. It still does not write to R2R.

## Apply mode

R2R writes require explicit `--apply`. No apply command exists in the current slice.

The R2R API probe is also read-only. It may inspect OpenAPI and list endpoints, but it must not create collections, ingest documents, update documents, delete documents, or archive anything.

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

Current dry-run metadata includes:

- project ID
- collection
- source path
- content SHA-256
- file size
- modified timestamp
- Git root
- Git branch
- Git commit
- Git dirty status
- remote URL when available

Git repositories remain the source of truth. R2R is rebuildable from cloned repos and project manifests.

## R2R Read Evidence

Before implementing comparison, `scripts/check_r2r_state.py` should be used to verify reachable read APIs and whether document metadata is available. Archive/inactive/version/delete/update support should be treated as evidence from OpenAPI, not as permission to call mutating endpoints.

## Read-Only Comparison

Comparison uses remote document metadata when available:

- `project_id`
- `collection`
- `source_path`
- `content_sha256`

Actions:

- `would_create`: no comparable remote metadata was found.
- `unchanged`: local and remote `content_sha256` match.
- `would_update`: `source_path` matches but `content_sha256` differs.
- `unknown_metadata`: remote metadata is missing fields needed for honest comparison.
- `stale_remote`: remote metadata has no matching local plan candidate; report-only.
- `missing_local`: manifest-listed local document is missing.
- `skipped`: local candidate is excluded by policy.

Stale remote documents are never deleted or archived by the compare command.
