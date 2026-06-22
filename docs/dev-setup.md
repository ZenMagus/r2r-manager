# Development Setup

Install:

`cd /home/w/projects/zenmagus/r2r-manager && python3 -m venv .venv && ./.venv/bin/python -m pip install --upgrade pip && ./.venv/bin/python -m pip install -e ".[dev]"`

Run tests:

`cd /home/w/projects/zenmagus/r2r-manager && ./.venv/bin/python -m pytest -q`

Build a dry-run plan for all registered projects:

`cd /home/w/projects/zenmagus/r2r-manager && ./.venv/bin/python scripts/plan_sync.py --config config/projects.example.yaml --all`

Build a JSON dry-run plan for voice-stack:

`cd /home/w/projects/zenmagus/r2r-manager && ./.venv/bin/python scripts/plan_sync.py --config config/projects.example.yaml --project voice-stack --json`

Probe local R2R read-only state:

`cd /home/w/projects/zenmagus/r2r-manager && ./.venv/bin/python scripts/check_r2r_state.py`

Probe local R2R read-only state as JSON:

`cd /home/w/projects/zenmagus/r2r-manager && ./.venv/bin/python scripts/check_r2r_state.py --json`

Start local R2R when needed:

`cd /home/w/projects/zenmagus/services/r2r && docker compose -f docker/compose.full.yaml --env-file docker/env/r2r-full.env --profile postgres up -d`

The service env should use `R2R_POSTGRES_HOST=postgres`.

Compare all local planned docs against R2R read-only metadata:

`cd /home/w/projects/zenmagus/r2r-manager && ./.venv/bin/python scripts/compare_r2r.py --config config/projects.example.yaml --all`

Compare voice-stack as JSON:

`cd /home/w/projects/zenmagus/r2r-manager && ./.venv/bin/python scripts/compare_r2r.py --config config/projects.example.yaml --project voice-stack --json`

The planning commands do not call R2R APIs. The probe and compare commands call only read-only GET endpoints and do not write to R2R.
