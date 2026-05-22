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
7. Compare against R2R metadata.
8. Plan add/update/unchanged/stale/delete actions.
9. Apply only when explicitly requested.

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
