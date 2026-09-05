# Nimbus – Mage.ai OSS Data Pipeline Project

<!-- WORKED EXAMPLE: the template filled in for a fictional project ("Nimbus
     Energy"). Nothing here is a real company, host or credential — it exists to
     show how much detail a filled-in CLAUDE.md should carry. -->

## General

For Mage.ai / dbt / Docker mechanics, rely on the `mage-dbt-conventions` skill.

## About Nimbus

Energy retailer: supplies electricity and gas to households and businesses.
Two companies under one brand: Nimbus Trading (`nimbus_trading`, trading) and
Nimbus Supply (`nimbus_supply`, supply). Usually referred to just as Nimbus.

## Domain knowledge (source systems)

- **The CRM** (used by traders) — all customer, contract, payment, invoicing
  data. Two installations (nimbus_trading + nimbus_supply), synced and unified;
  tables carry a `_source` column for origin.
- Supply point (SP) identifier = EAN or EIC code. One active contract per SP at a
  time; history may hold several. An SP is valid only with `date_start` set and
  `date_end` null-or-set AND status "effective"/"terminated"; a contract is valid
  only if its SP is valid.
- Soft deletes: most CRM tables have a `del` column that must be false.

## Architecture

- **Mage AI** (`NimbusMage/`): config → loader → exporter extraction pipelines.
- **dbt** (`NimbusMage/dbt/main_transformations/`): medallion layering below.

### dbt layers (this project)

| Folder | Naming | Purpose |
|---|---|---|
| `0_staging/` | `stg_<src>__*` | raw staging views/copies |
| `1_intermediate/` | `int__*`, `int__err_*` | cleansing, joins, validation |
| `2_marts/` | `dim_*`, `fct_*` | business entities, English names |
| `3_reporting/` | renamed cols | reporting views, localized column names |

## Infrastructure

Docker Compose, profiles `dev` / `prod` (commands in the skill).
- PostgreSQL runs on external host `192.0.2.10` (not in Docker in dev).
- Extra deps in Dockerfile: sshtunnel, mysqlclient, pymysql, paramiko==2.11.0,
  fdb (Firebird), + Node 20/yarn for frontend build.

## Connections & environment

- `io_config.yaml` not in repo (only `.example`); real file on server.
- `.env` not committed: PostgreSQL `192.0.2.10:5432`, DB `nimbus`, Mage auth,
  Slack/Teams webhooks.
- Sources: MySQL via SSH tunnel; Google Sheets; HTTP APIs (central bank rates,
  call center, postcodes…); CRM extractor.

### Querying databases (toolbox MCP)

- `toolbox-local.yaml` (dev) — tool `query_nimbus`.
- `toolbox-production.yaml` (prod, read-only) — tool `query_nimbus_production`.

## Production

- Mage UI: `https://mage.nimbus.example.com`
- **GlitchTip** — organization: `nimbus`, project: `nimbus-mage` (id 1).
  Prod tag `NimbusMage` (dev: `NimbusMageDev`) — triage prod first.
  Triage with `glitchtip-triage`.
- Notifications: Slack + MS Teams (localized templates).

## Power BI reports

(Nimbus has none currently — section omitted. If added: reports live in this repo
or in a dedicated reports repo, edited via the `powerbi-report-editing` skill.)

## Commit messages

Conventional Commits, no emojis — see `COMMIT-STANDARD.md`.

## Project-specific gotchas

- CRM validity: don't treat a contract as valid on its own — check its supply
  point first (dates + status), and `del = false` everywhere.
