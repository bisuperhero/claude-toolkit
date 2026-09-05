# {{PROJECT_NAME}} – Mage.ai OSS Data Pipeline Project

<!--
  UNIVERSAL TEMPLATE. Copy to <repo>/CLAUDE.md and fill in every placeholder.

  Faster: `/init-project` (mage-dbt-toolkit) drafts this file with everything it
  can read out of the repo already filled in, and leaves only the rest.

  Placeholders are all of one form: double braces around an UPPER_SNAKE name.
  Guidance on what belongs in each one is in HTML comments like this one, so
  when you are finished
      python3 <plugin>/scripts/init-project.py <repo> --check
  must come back clean. Delete the comments and any section that does not apply.

  Shared Mage.ai/dbt mechanics are NOT repeated here — they live in the
  `mage-dbt-conventions` skill (mage-dbt-toolkit plugin). Keep this file about
  THIS project only. See FILL-ME-CHECKLIST.md for the per-project steps.
-->

## General

For Mage.ai / dbt / Docker mechanics (block decorators, the config → loader →
exporter pattern, dbt layering, io_config rules, compose profiles), rely on the
`mage-dbt-conventions` skill — do not duplicate it here.

## About {{PROJECT_NAME}}

<!--
  BUSINESS_CONTEXT: one paragraph, plain terms — what the company or project
  does, enough for Claude to understand the domain. Optional for internal
  projects; delete the section rather than leaving it empty.
-->
{{BUSINESS_CONTEXT}}

## Domain knowledge (source systems)

<!--
  One bullet per important source system: what it is, the grain/identifier, the
  validity rules, the soft-delete flag, a multi-tenant `_source` column — the
  things Claude cannot infer from the code. Copy the bullet as many times as you
  have sources.
-->
- **{{SOURCE_SYSTEM}}** ({{SOURCE_SYSTEM_KIND}}) — {{SOURCE_SYSTEM_NOTES}}
- Soft deletes: {{SOFT_DELETE_RULE}}

## Architecture

- **Mage AI** (`{{MAGE_DIR}}`): {{PIPELINE_COUNT}} extraction pipelines,
  config → loader → exporter.
- **dbt** (`{{DBT_DIR}}`): medallion layering —
  the concrete mapping is below.
<!-- Secondary dbt project, if there is one; otherwise delete the next line. -->
- **Secondary dbt project**: {{SECONDARY_DBT_PROJECT}}

### dbt layers (this project)

<!--
  Fill in the actual folders and numbering for this repo — they differ per
  project (0–2 and 0–4 both happen, plus variants like `2_marts_v2/`). Delete
  rows you do not have.
-->

| Folder | Naming | Purpose |
|---|---|---|
| `{{STAGING_DIR}}` | `stg_<src>__*` | {{STAGING_PURPOSE}} |
| `{{INTERMEDIATE_DIR}}` | `int__*` | {{INTERMEDIATE_PURPOSE}} |
| `{{MARTS_DIR}}` | `dim_*`, `fct_*` | {{MARTS_PURPOSE}} |
| `{{REPORTING_DIR}}` | renamed cols | {{REPORTING_PURPOSE}} |

## Infrastructure

Docker Compose, profiles `dev` and `prod` (commands are in the
`mage-dbt-conventions` skill). Project-specific deviations:

<!--
  e.g. "PostgreSQL runs on external host 192.0.2.10, not in Docker in dev",
  extra services, non-standard ports, extra deps baked into the Dockerfile.
-->
- {{INFRA_DEVIATIONS}}

## Connections & environment

(io_config / .env mechanics: see the `mage-dbt-conventions` skill. Keep only
project-specific facts here.)

- PostgreSQL `{{DB_HOST}}:{{DB_PORT}}`, DB `{{DB_NAME}}`.
- Source DB access: {{SOURCE_DB_ACCESS}}

### Querying databases (toolbox MCP)

- Dev tool `{{TOOLBOX_DEV_TOOL}}`.
- Prod tool `{{TOOLBOX_PROD_TOOL}}` (read-only).
<!-- e.g. "dev is a truncated sample"; delete the line if there is no caveat. -->
- {{TOOLBOX_CAVEATS}}

## Production

- Mage UI: `{{PROD_URL}}`
- **GlitchTip** — organization: `{{GLITCHTIP_ORG}}`, project:
  `{{GLITCHTIP_PROJECT}}`. Prod `server_name`/environment tag: `{{PROD_TAG}}`
  (dev: `{{DEV_TAG}}`). Triage with the `glitchtip-triage` skill.
- Notification channels: {{NOTIFICATION_CHANNELS}}

## Power BI reports

<!-- Only if this project has reports; otherwise delete the whole section. -->

- Reports live in `{{PBI_REPORTS_DIR}}` (PBIP layout: `*.pbip`, `*.Report/`,
  `*.SemanticModel/`), either in this repo or in a dedicated reports repo.
- Edit with the `powerbi-report-editing` skill (powerbi-toolkit plugin).
- Layout conventions for this project: see `POWERBI-LAYOUT.md` (created on first
  use).

## Commit messages

Conventional Commits, no emojis — see `COMMIT-STANDARD.md`.

## Project-specific gotchas

<!--
  Start empty and add each one as you hit it: the things that look safe but are
  not, and the reasoning behind non-obvious choices. This section is the main
  reason this file exists — everything above can be re-derived, this cannot.
-->
- {{GOTCHAS}}
