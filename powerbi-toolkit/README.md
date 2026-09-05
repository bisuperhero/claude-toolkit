# powerbi-toolkit

Shared Claude Code setup for editing Power BI reports and semantic models (PBIR /
TMDL) directly from a project repo — across any project, not just one.

Separate from `mage-dbt-toolkit` on purpose: report editing is orthogonal to the
data pipeline. A project may have data work, report work, or both — install only
what it needs.

## What's inside

```
powerbi-toolkit/
├── .claude-plugin/plugin.json
├── commands/
│   ├── preflight.md                 # /preflight — are the external tools installed, and what does each missing one cost?
│   ├── doctor.md                    # /doctor — run every check over the repo and triage the result
│   ├── describe-measures.md         # /describe-measures — write missing measure descriptions, backfill DAX blocks
│   └── measure-catalog.md           # /measure-catalog — build or refresh the measure catalog, then verify it
└── skills/
    └── powerbi-report-editing/
        ├── SKILL.md                     # router: where things live, tools, safe edit protocol, pre-commit checks
        ├── references/
        │   ├── pbir-visuals.md          # visual.json projections, tables, cards, naming, slicers, series colors
        │   ├── themes-and-validate.md   # theme JSON cards + how to read the PBIR validator
        │   ├── tmdl-and-model.md        # te gotchas, TMDL syntax, M escaping, DAX pitfalls, measure descriptions
        │   ├── desktop-bridge.md        # driving a running Desktop, reload semantics, screenshot loop
        │   ├── page-refactor.md         # rebuild an existing page onto the current layout
        │   ├── bulk-tools.md            # the scripts that write: naming, DAX blocks
        │   ├── measure-catalog.md       # INFO.VIEW.MEASURES catalog behind a report help page / data dictionary
        │   ├── modeling-mcp.md          # optional MCP server for live semantic-model work
        │   ├── thin-reports.md          # live connection to a published model
        │   ├── pbix-packaging.md        # editing and repacking a .pbix
        │   ├── service-facts.md         # what Power BI Service facts a project should track, and what Pro's API can't tell you
        │   ├── generated-page-furniture.md  # script-generated headers/nav instead of hand-editing repeated page elements
        │   └── layout-standard-template.md  # DEFAULT layout/formatting template, copied into a project on first use
        └── scripts/                     # 11 scripts + _common.py
            ├── preflight.py                 # are the external tools installed? versions, what breaks, how to install
            ├── doctor.py                    # runs every check below, one prioritized report (--tools runs preflight)
            ├── check-visual-projections.py  # broken projections, missing cross-filter, unnamed visuals
            ├── check-m-escaping.py          # un-doubled quotes in SQL inside M partitions
            ├── check-layout-file.py         # is the project's layout file present, current, and its own?
            ├── check-measure-descriptions.py # description coverage + anti-patterns
            ├── check-theme-drift.py         # do all reports use the same theme version?
            ├── find-theme-overrides.py      # per-visual formatting that fights or duplicates the theme
            ├── name-visuals.py              # bulk: name every visual for the Selection pane
            ├── backfill-dax-blocks.py       # bulk: copy each measure's DAX into its description
            └── measure-catalog.py           # build/refresh the measure catalog table (also `--check`)
```

The references are loaded on demand — `SKILL.md` says which one to read for the
task at hand, so a theme tweak doesn't pull in the whole corpus.

## Install

```
/plugin marketplace add bisuperhero/claude-toolkit
/plugin install powerbi-toolkit@bisuperhero-claude-toolkit
```

## How it works

- **Reports location**: stated in the project's `CLAUDE.md`. The reports either sit
  in the root of their own git repo, or in a reports folder inside the project
  repo; either way git is the source of truth.
- **Tools** (Tabular Editor CLI, PBIR authoring CLI, Desktop bridge) are assumed
  installed machine-wide; the skill uses, doesn't install them. `preflight.py`
  (also `doctor.py --tools`, also `/powerbi-toolkit:preflight`) says which of them
  this machine actually has, at what version, and what each missing one costs —
  run it before a task needs one, not after `command not found`.
- **Layout and formatting are per-project and live only in the project.** The skill
  itself carries no page sizes, gaps, fonts, colors or naming conventions. On first
  use it generates `POWERBI-LAYOUT.md` from the default template and asks you to
  review it; from then on that file is authoritative — it outranks the skill and
  the PBIR validator alike. Projects legitimately differ.
- **Checks are scripts, not good intentions.** `doctor.py` runs the seven checkers
  over the whole repo before a commit; they are calibrated against production
  reports (zero false positives across ~5 800 visuals in five repos) so their
  output stays worth reading.

## Supported environments

The offline half — every checker, TMDL and PBIR editing, the bulk tools — runs on
Linux, macOS, WSL and Windows with Python 3.8+ and needs nothing else installed.

Anything touching a **live** model or a running Desktop needs Power BI Desktop,
which is Windows-only: either Windows itself, or WSL2 with access to the Windows
host. On macOS and plain Linux there is no Desktop to drive, so the safe-edit
protocol, screenshots and the catalog's final verification are out of reach.

### What still works without which tool

| Missing | Still works | Doesn't |
|---|---|---|
| Tabular Editor (`te`) | all checkers, `name-visuals.py`, `measure-catalog.py`, `backfill-dax-blocks.py` without `--format` | `backfill-dax-blocks.py --format`, scripted `te` model edits |
| `powerbi-report-author` | everything else | `preview-visuals` / `preview-pages` / `preview-filters` / `preview-themes`, `validate` |
| Power BI Desktop / the bridge | everything offline | the safe edit protocol's `status` check, `reload`, screenshots, verifying a built catalog |
| Power BI Modeling MCP (optional) | everything offline; live work falls back to the bridge or `te.exe --local` | MCP-driven edits to a live model |

`preflight.py` reports exactly these rows for the machine it runs on, so the two
never drift apart. An **expired** Tabular Editor counts as missing — see below.

An expired `te` is the failure mode worth knowing about in advance: the tested
0.5.2 is an **early preview build that stops running on a fixed date** (this copy:
2026-09-30). After that `te format` and offline TMDL operations fail with nothing
naming the cause, so download a newer build from
<https://tabulareditor.com/downloads> now and then. `preflight.py` reads the date
out of `te`'s own banner and warns inside 30 days.

## Non-goals

- No deployment to the Power BI Service — no publishing, no dataset refresh
  orchestration, no workspace management.
- No editing of a legacy `.pbix` as a binary. Pre-PBIR `Report/Layout` blobs and
  the `DataModel` part stay untouched.
- No offline DAX validation. Nothing here parses or type-checks DAX without a
  live model; that is Desktop's or the Modeling MCP's job.
