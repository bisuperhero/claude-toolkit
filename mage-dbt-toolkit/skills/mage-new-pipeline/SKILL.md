---
name: mage-new-pipeline
description: 'Scaffold a new Mage.ai extraction pipeline in a Mage/dbt project. Use when creating a new pipeline, onboarding a new data source, or extracting from Google Sheets, PostgreSQL, MySQL, MSSQL, Firebird or an HTTP API into the warehouse, or when copying an existing pipeline as a template (e.g. ex_gsheet_*). Also matches Czech prompts such as "nová pipeline" or "extrakce z...". Copies the closest existing pipeline: standard sources get config → loader → exporter; streaming DB extractors get config + streaming loader (two blocks), plus metadata.yaml wiring and triggers.yaml. Not for dbt models — use mage-dbt-conventions.'
---

# Scaffold a new Mage extraction pipeline

Create a new extraction pipeline consistent with the project's existing ones. The
golden rule: **find the closest existing pipeline of the same source type and copy
its structure** — the surrounding plumbing (decorators, config keys, schema
routing, triggers) is already correct. Don't invent a layout.

## Step 0 — preflight

If you'll need to inspect source/target tables or test the new pipeline against the
DB, confirm the toolbox query tool (`query_<db>`) is available first (see
`mage-dbt-conventions`). If the toolbox MCP isn't connected, you can still scaffold
the files from existing pipelines, but tell the user DB inspection/testing is
unavailable until they start it.

## Step 1 — gather inputs

Ask for whatever isn't given:
- Source type: Google Sheets / PostgreSQL / MySQL / MSSQL / Firebird / HTTP API.
- Pipeline name (follow existing convention, e.g. `ex_gsheet_<name>`,
  `ex_<source>_<entity>`).
- Target schema + table.
- Load method: `full` / `incremental` / `hash` (see `mage-dbt-conventions`).
- For Sheets: document URL + sheet/list name(s).
- For DB sources: source table, key column(s), incremental watermark column.

## Step 2 — pick the template pipeline

Locate existing pipelines of the same source type (search `data_loaders/`,
`custom/`, `pipelines/`). Pick the closest match and read its blocks. Mirror its
config keys, naming, logging, and error handling. **Use the project's logger, not
`print`.**

## Step 3 — choose block structure by source type

There are **two shapes**. Get this right:

### A. Standard source → THREE blocks: config → loader → exporter

For Google Sheets, HTTP APIs, and any source read fully into a DataFrame:
1. **Config block** (`custom/`): returns `PIPELINE_CONFIG` (source ref, load
   method, target schema/table, keys). `@custom`.
2. **Data loader** (`data_loaders/`): reads the source into a DataFrame. `@data_loader`.
3. **Data exporter** (`data_exporters/`): writes the DataFrame to PostgreSQL using
   the load method. `@data_exporter`.

### B. Streaming extractor → TWO blocks: config + streaming loader

For the high-volume DB extractors (`a_postgresql_streaming_extractor`,
`a_mssql_streaming_extractor`, `a_firebird_streaming_extractor`): the streaming
loader reads **and writes** in chunks itself — there is **no separate exporter
block**.
1. **Config block** (`custom/`): same role as above (source table, keys, schema,
   load method, batch size).
2. **Streaming loader**: streams rows from the source straight into the target in
   batches. This single block owns both read and write.

Do not add a third exporter block to a streaming extractor — the test/run will
fail. (Conversely, a standard source needs all three; a config + two non-streaming
blocks is wrong too.)

## Step 4 — generate the files

- Create the block files in the right folders with correct decorators.
- Create the pipeline dir under `pipelines/<name>/`: `metadata.yaml` (block graph
  wiring), `__init__.py`, and a `triggers.yaml` matching the project's standard
  (e.g. an inactive/manual "FULL LOAD" trigger reading `forced_full_load`).
- Match the block-graph wiring in `metadata.yaml` to the chosen shape (3 nodes vs
  2 nodes).

## Step 5 — sanity checks

- Every block has the correct decorator (`@custom` / `@data_loader` /
  `@transformer` / `@data_exporter`).
- Streaming = 2 blocks, standard = 3 blocks — verify the count matches the source
  type.
- `io_config.yaml` / secrets are referenced the project's way (don't hardcode
  credentials; `io_config.yaml` is not in the repo).
- Suggest a test run on a small batch before wiring into the main orchestration.
- Commit per `COMMIT-STANDARD.md` (e.g. `feat(loader): add ex_gsheet_rls pipeline`).
