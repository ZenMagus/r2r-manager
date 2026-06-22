# r2r-manager Architecture

`r2r-manager` syncs project documentation from local Git repositories into R2R.

## Principle

Git is the canonical versioned source. R2R is a searchable projection.

## Data flow

1. Read registered project config.
2. Follow project symlinks under `projects/`.
3. Read each project's `docs/project-knowledge-manifest.md`.
4. Discover canonical docs.
5. Compute `content_sha256`.
6. Read Git metadata.
7. Build a dry-run plan with `would_update_unknown`, `missing`, and `skipped` actions.
8. Compare against R2R read-only document metadata when requested.
9. In a later apply slice, write only when explicitly requested.

## Current implementation

Implemented now:

- `app/project_config.py` loads registered project config and validates symlink targets.
- `app/project_manifest.py` reads `docs/project-knowledge-manifest.md` and extracts the `Canonical Docs To Ingest Later` list.
- `app/document_discovery.py` builds document candidates and excludes generated/runtime paths.
- `app/git_metadata.py` collects repo branch, commit, dirty status, remote URL, file size, modified time, and content SHA-256.
- `app/sync_plan.py` produces a dry-run plan.
- `scripts/plan_sync.py` prints readable or JSON dry-run output.
- `app/r2r_config.py` reads local R2R probe configuration.
- `app/r2r_client.py` provides read-only GET methods only.
- `app/r2r_probe.py` reports reachable/auth/OpenAPI/collection/document capability evidence.
- `scripts/check_r2r_state.py` prints the read-only probe report.
- `app/r2r_compare.py` compares local candidates against remote document metadata without mutation.
- `scripts/compare_r2r.py` prints readable or JSON read-only comparison output.

Not implemented yet:

- R2R mutating API calls.
- apply mode.
- stale/delete handling.
- auto-sync hooks.
- NATS message handling.

The read-only probe and comparison may call `/v3/health`, OpenAPI endpoints, and collection/document list endpoints. They do not call create, update, delete, ingest, or archive endpoints.

## Versioning strategy

R2R document records should include:

- project_id
- collection
- source_path
- git_branch
- git_commit
- git_dirty
- content_sha256
- doc_status
- ingested_at
- owner_project

If R2R supports inactive/archive status, `r2r-manager` may use it later. Until verified, stale handling should be modeled in `r2r-manager` metadata and deletion should require explicit approval.

## New dev box recovery

A new dev box should be able to:

1. Clone active source repos.
2. Clone `r2r-manager`.
3. Recreate project symlinks.
4. Point `r2r-manager` at local R2R.
5. Rebuild R2R collections from Git-tracked docs.
