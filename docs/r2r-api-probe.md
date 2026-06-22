# R2R API Probe

`r2r-manager` includes a read-only R2R API probe. It is used to learn what local R2R APIs are reachable before implementing any compare/apply path.

## Local Configuration

The local service notes under `/home/w/projects/zenmagus/services/r2r/R2R_LOCAL_NOTES.md` identify:

- R2R API: `http://localhost:7272`
- dashboard: `http://localhost:7273`
- health check: `http://localhost:7272/v3/health`

`r2r-manager` therefore defaults to `R2R_BASE_URL=http://localhost:7272`.

Start local R2R with:

`cd /home/w/projects/zenmagus/services/r2r && docker compose -f docker/compose.full.yaml --env-file docker/env/r2r-full.env --profile postgres up -d`

The compose env should use `R2R_POSTGRES_HOST=postgres`, not `localhost`, because R2R runs inside Docker and connects to the Postgres compose service.

Optional environment variables:

- `R2R_BASE_URL`
- `R2R_TIMEOUT_SECONDS`
- `R2R_WRITE_TIMEOUT_SECONDS`
- `R2R_API_KEY`
- `R2R_TOKEN`

Secrets are not hardcoded. If an API key or token is set, the read-only client sends it as a bearer token.

## Read-Only Endpoints

The probe may issue GET requests only:

- `/v3/health`
- `/openapi.json`
- `/openapi_spec`
- `/v3/collections?limit=10&offset=0`
- `/v3/documents?limit=10&offset=0`

It does not call POST, PUT, PATCH, or DELETE endpoints.

The read-only comparison command also calls only document list GET endpoints.

## Confirmed Write Endpoint Evidence

Local source inspection shows:

- `POST /v3/documents` creates a document from a file, raw text, or chunks with metadata and optional collection IDs.
- `PUT /v3/documents/{id}/metadata` replaces metadata only.
- `PATCH /v3/documents/{id}/metadata` appends metadata only.
- `DELETE /v3/documents/{id}` exists but is out of scope and must not be called by r2r-manager's cautious sync path.

`apply_r2r_sync.py` uses this evidence conservatively. It may call `POST /v3/documents` only when `--apply` is present and the target collection already exists. It does not call metadata replacement as a substitute for content update. It does not delete, archive, create collections, or mutate stale remote docs.

The document create form receives `collection_ids` as a JSON-encoded list. YAML is not listed in R2R's `DocumentType`, so r2r-manager presents `.yaml` and `.yml` files as `text/plain` with `.txt` upload filenames while preserving their original source metadata.

## Evidence Report

The probe reports:

- whether R2R is reachable
- whether auth appears required
- whether OpenAPI is available
- whether collection/document read APIs appear supported
- whether metadata fields are evidenced
- whether archive/inactive/version terms appear in OpenAPI
- whether update/delete endpoints are evidenced in OpenAPI

Update/delete/archive evidence is informational only for probe and compare commands. No mutating endpoint is called by either command.

## Commands

Text output:

`cd /home/w/projects/zenmagus/r2r-manager && ./.venv/bin/python scripts/check_r2r_state.py`

JSON output:

`cd /home/w/projects/zenmagus/r2r-manager && ./.venv/bin/python scripts/check_r2r_state.py --json`

## Future Work

Future work should confirm a safe document-content replacement endpoint before enabling `would_update`. Delete/stale/archive behavior must not be assumed until R2R support and operator policy are verified.
