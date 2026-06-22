# Sync Policy

## Default mode

Dry-run only.

`plan_sync.py` only plans local candidates. It reports `would_update_unknown` for readable docs because it intentionally does not call R2R.

`compare_r2r.py` performs live read-only comparison against R2R document metadata. It still does not write to R2R.

## Apply mode

R2R writes require explicit `--apply`.

`apply_r2r_sync.py` is dry-run by default. In dry-run mode it may probe and list R2R state, but it must not call mutating endpoints.

With `--apply`, the first supported mutation is limited to `would_create` documents through confirmed `POST /v3/documents` support. The command does not create collections; the target collection must already exist. `would_update` is reported but skipped with `content_update_endpoint_unknown` until a safe document-content replacement endpoint is confirmed.

Write calls are never retried automatically. If a create times out or fails after the request is sent, the report uses `r2r_write: attempted` and `remote_state: unknown`. The operator must run `compare_r2r.py` before another apply. Documents that were actually ingested will compare as `unchanged` and will not be retried.

Confirmed write endpoint evidence:

- `POST /v3/documents` accepts a file/raw text/chunks, metadata, collection IDs, and `run_with_orchestration`.
- `PUT /v3/documents/{id}/metadata` replaces metadata but does not replace document content.

The R2R API probe is read-only. It may inspect OpenAPI and list endpoints, but it must not create collections, ingest documents, update documents, delete documents, or archive anything.

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

Current sync metadata includes:

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
- source modified time
- source size in bytes
- r2r-manager schema/version marker
- ingest tool
- ingest mode / sync mode

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

## Cautious Create/Update Sync

`apply_r2r_sync.py` consumes the read-only comparison and produces operation statuses:

- `dry_run`: an eligible create would be attempted in apply mode.
- `created`: an eligible create succeeded in apply mode.
- `skipped_update`: a changed document was not updated because content replacement is not confirmed.
- `skipped_stale_remote_report_only`: stale remote metadata was reported only.
- `skipped_unknown_metadata`: remote metadata was incomplete and no mutation was attempted.
- `skipped_missing_collection`: the target collection was not found and was not created automatically.
- `error`: an eligible create failed and was recorded without deleting or archiving anything.

Collection IDs are serialized as a JSON list for R2R's `Json[list[UUID]]` multipart field. YAML source docs are uploaded as `text/plain` with a `.txt` upload filename because YAML is not a supported R2R `DocumentType`; original paths and hashes remain in metadata.

Read timeout configuration uses `R2R_TIMEOUT_SECONDS` (default `5`). Write timeout configuration uses `R2R_WRITE_TIMEOUT_SECONDS` (default `300`).

No current command deletes, archives, mutates stale remote docs, creates collections, or performs auto-sync.
