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
- Plan R2R sync actions: add, update, unchanged, stale/inactive, delete if explicitly requested.
- Sync docs into R2R only when explicitly requested with apply-style commands.
- Rebuild R2R collections from cloned Git projects on a new dev box.

## Non-goals for initial version

- Do not make R2R the source of truth.
- Do not auto-ingest on every file change.
- Do not delete R2R documents by default.
- Do not ingest secrets, generated artifacts, datasets, audio, model files, or private runtime configs.
