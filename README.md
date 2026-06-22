# r2r-manager

`r2r-manager` is the local synchronization controller for project documentation that should be indexed into R2R.

Git repositories remain the source of truth. R2R is treated as a searchable/indexed projection of committed docs.

## Canonical source path

`/home/w/projects/zenmagus/r2r-manager`

## Service/deployment path

`/home/w/projects/zenmagus/services/r2r-manager -> /home/w/projects/zenmagus/r2r-manager`

## Registered project symlinks

Project access is intentionally opt-in through symlinks under `projects/`:

- `projects/edub -> ../../edub`
- `projects/voice-stack -> ../../voice-stack`
- `projects/autodub -> ../../autodub`
- `projects/local-runtime-manager -> ../../local-runtime-manager`

## Intended responsibilities

- Read project knowledge manifests.
- Discover canonical docs for each registered project.
- Compute content hashes.
- Collect Git metadata: repo, branch, commit, dirty status, source path.
- Plan dry-run R2R sync candidates.
- Sync docs into R2R only when explicitly requested with apply-style commands.
- Rebuild R2R collections from cloned Git projects on a new dev box.

## Non-goals for initial version

- Do not make R2R the source of truth.
- Do not auto-ingest on every file change.
- Do not delete R2R documents by default.
- Do not ingest secrets, generated artifacts, datasets, audio, model files, or private runtime configs.

## Current dry-run planner

The first implemented slice is dry-run discovery only. It loads `config/projects.example.yaml`, follows registered project symlinks under `projects/`, reads `docs/project-knowledge-manifest.md`, computes document SHA-256 hashes, collects Git branch/commit/dirty metadata, and prints a sync plan.

It does not call R2R APIs, compare against R2R state, write documents to R2R, delete R2R records, or install hooks.

Run all registered projects:

```bash
./.venv/bin/python scripts/plan_sync.py --config config/projects.example.yaml --all
```

Run one project as JSON:

```bash
./.venv/bin/python scripts/plan_sync.py --config config/projects.example.yaml --project voice-stack --json
```

## Current read-only R2R probe

`r2r-manager` can also probe the local R2R API in read-only mode. The default base URL is `http://localhost:7272`, discovered from `/home/w/projects/zenmagus/services/r2r/R2R_LOCAL_NOTES.md` and the local compose config. The probe uses GET requests only and does not ingest, update, or delete anything.

Start the local R2R stack from the service repo when needed:

```bash
cd /home/w/projects/zenmagus/services/r2r && docker compose -f docker/compose.full.yaml --env-file docker/env/r2r-full.env --profile postgres up -d
```

The local env should keep `R2R_POSTGRES_HOST=postgres` because the R2R container reaches Postgres by compose service name.

```bash
./.venv/bin/python scripts/check_r2r_state.py
```

```bash
./.venv/bin/python scripts/check_r2r_state.py --json
```

## Current read-only comparison

`scripts/compare_r2r.py` compares the local dry-run plan against R2R document metadata using GET requests only. Matching is based on remote metadata fields `project_id`, `collection`, `source_path`, and `content_sha256`.

It reports `would_create`, `would_update`, `unchanged`, `unknown_metadata`, `missing_local`, `skipped`, and report-only `stale_remote`. It does not create collections, ingest documents, update documents, archive documents, delete documents, or call mutating R2R endpoints.

```bash
./.venv/bin/python scripts/compare_r2r.py --config config/projects.example.yaml --all
```

```bash
./.venv/bin/python scripts/compare_r2r.py --config config/projects.example.yaml --project voice-stack --json
```
