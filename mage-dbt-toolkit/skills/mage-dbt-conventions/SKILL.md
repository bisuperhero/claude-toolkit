---
name: mage-dbt-conventions
description: Shared conventions for Mage.ai (OSS) + dbt + PostgreSQL data pipeline projects. Use when working in any Mage/dbt repo — editing pipeline blocks (data_loaders, transformers, data_exporters, config blocks), load methods (full / incremental / hash, forced_full_load), dbt models across the staging → intermediate → marts → reporting layers, dbt run/test/compile, macros and sources.yml, io_config / .env / Mage secrets, metadata.yaml, or the Docker Compose dev/prod stack. Also for querying the warehouse or a source database through the toolbox MCP (query_<db> tools). Covers project-agnostic mechanics; project-specific facts (sources, prod URL, schemas) live in the project's CLAUDE.md. For scaffolding a brand-new extraction pipeline, use mage-new-pipeline.
---

# Mage.ai + dbt project conventions

This skill captures the mechanics shared across all Mage.ai OSS + dbt + PostgreSQL
projects. Anything project-specific (data sources, production URL, GlitchTip name,
exact dbt layer numbering, secrets) lives in that project's `CLAUDE.md`, not here.

## Repo shape (typical)

```
<Project>Mage/                  # mounted as USER_CODE_PATH
├── metadata.yaml               # Mage project config + notifications (Slack/Teams)
├── io_config.yaml.example      # connection template — real io_config.yaml is NOT in repo
├── pipelines/                  # pipeline definitions (YAML + python)
├── custom/                     # config blocks + shared python utilities
├── data_loaders/               # extract from source DB / API
├── transformers/               # in-flight transforms (optional)
├── data_exporters/             # write to PostgreSQL warehouse
└── dbt/main_transformations/   # dbt project (models/, macros/, profiles.yml)
docker-compose.yml              # dev + prod profiles
Dockerfile                      # custom image on top of mageai/mageai:latest
.env                            # NOT committed
```

## Mage.ai block rules (non-negotiable)

- Every pipeline block is a python function with the correct decorator:
  `@data_loader`, `@transformer`, or `@data_exporter`. A block without its
  decorator will not run.
- A test block uses `@test` and asserts on the output of the block above it.
- Blocks pass data positionally: a downstream block receives upstream outputs as
  its first arguments. Keep return types stable (usually a `pandas.DataFrame`).
- `kwargs` carries runtime context (e.g. `execution_date`, pipeline variables).

## Extraction pipeline pattern

Standard extraction pipelines follow **config → loader → exporter** (3 blocks);
high-volume DB **streaming extractors** are config + streaming loader (2 blocks, no
separate exporter). The config block (`custom/`) returns `PIPELINE_CONFIG` (source,
load method, target schema, keys); source DB access is commonly tunneled with
`sshtunnel` + `paramiko`. For the full block-by-block scaffolding procedure use the
`mage-new-pipeline` skill.

Load methods:
- `full` — truncate + reload the whole table.
- `incremental` — append/upsert rows newer than the last watermark.
- `hash` — compare row hashes to detect changes (for sources without a reliable
  updated-at column).

To force a one-off full reload of an incremental extractor, projects expose a
`forced_full_load` runtime variable (read in the config/loader block) — set it on
the pipeline run rather than editing the load method. A standard inactive/manual
"FULL LOAD" trigger may already exist per pipeline.

When adding a new source, copy the closest existing config/loader/exporter trio
rather than writing from scratch — the surrounding plumbing is already correct.

## dbt layering (medallion)

All projects use a layered medallion structure under
`dbt/main_transformations/models/`. The **principle is constant**; the exact
folder numbering and the topmost layer name differ per project, so read the
project's `CLAUDE.md` / `dbt_project.yml` for the concrete mapping.

| Conceptual layer | Naming         | Purpose                                                        |
|------------------|----------------|---------------------------------------------------------------|
| staging          | `stg_<src>__*` | One model per source table; raw cleansing, typing, renaming.  |
| intermediate     | `int__*`       | Joins, business logic, validation/error models (`int__err_*`).|
| marts / core     | `dim_*`,`fct_*`| Business entities — dimensions and facts, English names.      |
| reporting        | (renamed cols) | Thin views for BI (often localized column names, e.g. Power BI). |

Conventions that hold across projects:
- Schema routing is defined in `dbt_project.yml` (staging → `stg_<src>` schemas,
  etc.). Don't hard-code schema names in models.
- Common cleansing macros live in `macros/` (e.g. `convert_an_to_bool()`,
  `trim_nullify_all_columns()`). Reuse before writing new ones.
- Sources are declared in per-domain `sources.yml` inside staging subfolders.
- dbt runs as the final step of the main orchestration pipeline.

Useful dbt commands (run from the dbt project dir, usually via the project venv):

```bash
dbt run --select model_name          # one model
dbt run --select +model_name         # model + upstream deps
dbt run --select model_name+         # model + downstream deps
dbt test --select model_name         # tests for one model
dbt compile --select model_name      # compile SQL without running
```

## Config & secrets

- `io_config.yaml` is **never committed** — only `io_config.yaml.example` is.
  The real file lives on the server with credentials. Don't recreate it from the
  example unless asked; don't print or commit its contents.
- `.env` is not committed either. Connection vars (PostgreSQL host/port/db/user/
  password, Mage auth, notification webhooks) come from there.
- dbt `profiles.yml` reads connection details from environment variables.
- **`.env` is read only at container creation** (`env_file:`). After editing
  `.env`, `docker compose restart` does NOT pick up changes — recreate:
  `docker compose up -d --force-recreate --no-deps <magic-test|magic>`.
- Mage's `get_secret_value(name)` reads ONLY Mage's Secret store (registered in the
  UI), not `.env`/`os.environ`, and raises outside a pipeline run. For values that
  live in `.env` (e.g. `SMTP_*`), read `os.environ.get(...)` directly instead.

## Docker Compose

Two profiles in `docker-compose.yml`:

```bash
docker compose --profile dev up -d    # dev — Mage UI on :6789 directly
docker compose --profile prod up -d   # prod — behind Traefik (HTTPS), + monitoring
```

`prod` typically also brings up Postgres (SSL), Traefik + Let's Encrypt, and the
Prometheus exporters. The custom `Dockerfile` adds python deps beyond the base
image (commonly `sshtunnel`, `pymysql`/`mysqlclient`, `paramiko`, `fdb` for
Firebird) plus Node for the frontend build.

## Database access (toolbox MCP)

Connect to the warehouse / source DBs through the **toolbox** MCP server, NOT by
hand-rolling psql. Each repo keeps its connection config in the project root:

- `toolbox-local.yaml` — local / dev database.
- `toolbox-production.yaml` — production database.

**Preflight (before the first DB query):** confirm a toolbox query tool is actually
available — list the MCP tools and look for `query_<db>` (the project's `CLAUDE.md`
names it). If none is present, the toolbox MCP isn't connected for this project:
tell the user to start it (it reads `toolbox-local.yaml` / `toolbox-production.yaml`
from the repo root) and stop, rather than falling back to raw psql or failing
mid-task.

These files define the toolbox sources and the queryable tools. Use the local one
for routine work; only reach for production when explicitly required, and treat it
as read-only unless told otherwise. The exact tool names are generated from the
yaml (commonly `query_<db>` / `query_<db>_production`); list available MCP tools to
get the precise names for the current project rather than guessing.

## Querying through the toolbox (Postgres)
- The prod tool is a read-only role with `statement_timeout`; dev is a truncated sample — use prod for validation, not for exploration.
- `TaskStop` kills only the MCP client; the query keeps running on the server. After `TaskStop`, check `pg_stat_activity` and, if needed, `pg_cancel_backend(pid)` (only when the user says so).
- Rewrite a correlated aggregate (`LEFT JOIN LATERAL`, subquery) over a large table as a standalone `GROUP BY` CTE and join that.
- Don't start another heavy query while the previous one is still hanging. Never run two `dbt run`s in parallel.
- Rankings: explicit `NULLS LAST`. A double `BEGIN` in the log is dbt, not an error.
- GlitchTip: fingerprint per run; Mage triggers aren't in the repo; orphaned block run = check the pipeline UUID.