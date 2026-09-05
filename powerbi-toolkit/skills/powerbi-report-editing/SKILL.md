---
name: powerbi-report-editing
description: "Edit Power BI reports and semantic models as source files (PBIP: PBIR JSON + TMDL) from the repo. Use for any Power BI change — report layout, page size and grid, visual sizing and alignment, slicers, themes and formatting, naming visuals for the Selection pane, refactoring a page to a design standard, measures and DAX, measure descriptions and a self-updating measure catalog / help page, TMDL tables and columns, M / Power Query partitions, thin reports on a live connection, repacking a .pbix, driving Power BI Desktop (reload, screenshot), or checking a report before commit (broken projections, missing columns, M escaping, theme drift). Also for diagnosing \"the visual shows fewer fields than it should\" or \"Desktop won't open the project\". Uses Tabular Editor CLI, the PBIR authoring CLI, the Desktop bridge and the optional Modeling MCP. Not for dbt/data pipeline work — that's mage-dbt-conventions."
---

# Power BI report editing

Edit Power BI reports and semantic models directly on their source files (PBIR
JSON for the report layer, TMDL for the model), driven from the repo. The tooling
is installed machine-wide; this skill is about using it safely and consistently.

This file is the router. The detail — and every gotcha that has already cost a
debugging session — lives in `references/`; **read the relevant one before
editing**, not after something renders wrong.

| Doing this | Read first |
|---|---|
| About to run `te`, `powerbi-report-author` or the bridge for the first time in a session | run `scripts/preflight.py` (step 0b below) |
| Authoring/editing `visual.json`, page layout | `references/pbir-visuals.md` |
| Editing theme JSON, or reading `validate` output | `references/themes-and-validate.md` |
| Rebuilding an existing page onto the current layout | `references/page-refactor.md` |
| Bulk cleanup: naming visuals, backfilling DAX blocks | `references/bulk-tools.md` |
| Editing TMDL, measures, DAX, M partitions; running `te` | `references/tmdl-and-model.md` |
| Surfacing measure descriptions in a report — a help page / data dictionary | `references/measure-catalog.md` |
| Driving Power BI Desktop, reload/screenshot loops | `references/desktop-bridge.md` |
| Editing a **live** model (open in Desktop / in the service) | `references/modeling-mcp.md` |
| A report with no `.SemanticModel/` (live connection) | `references/thin-reports.md` |
| Editing inside a `.pbix` file | `references/pbix-packaging.md` |
| Finding/recording workspace, dataset, credential or automation facts about the Service | `references/service-facts.md` |
| The same header/nav/footer element repeats across many pages | `references/generated-page-furniture.md` |

## Where the reports live

**The project's `CLAUDE.md` says where — read it first.** The reports either sit
in the root of their own git repo, or in a reports folder inside the project repo
(placeholder `{{PBI_REPORTS_DIR}}`, e.g. `powerbi_reports/`). Either way git is the
source of truth and changes are committed there.

- Format is PBIP: `*.pbip`, `*.Report/` (PBIR, granular
  `definition/pages/<id>/visuals/<id>/visual.json`), `*.SemanticModel/` (TMDL).
- **Only touch the report files when the task is editing a report/model.** Ignore
  them otherwise — they are large and every grep pays for it.

## What is editable

Classify by **content, not by file extension**. A `.pbix` is an OPC zip, not an
opaque binary: its `Report/definition/…` is editable PBIR, its legacy
`Report/Layout` blob is not, and its `DataModel` never is. So look inside before
declining to edit one — `unzip -Z1 file.pbix`, or `python3 -m zipfile -l file.pbix`
where `unzip` is missing (Windows). Full classification, and the hard requirement
for repacking: `references/pbix-packaging.md`.

## Step 0 — the project's layout file (mandatory, before any formatting work)

**This skill holds no layout or formatting values** — page size, gaps, title band,
slicer sizes and modes, minimum visual heights, fonts, colors and naming language
are a per-project design system. The skill describes *mechanics*; the project file
decides *values*. So before the first layout, sizing, naming or formatting change:

1. Look for the project's layout file — `POWERBI-LAYOUT.md` beside the reports, or
   a "Power BI layout" section in the project's `CLAUDE.md`.
2. **If it does not exist, generate it before doing the work**: copy
   `references/layout-standard-template.md` into the project as
   `POWERBI-LAYOUT.md`, substitute `{{PROJECT_NAME}}` and any other placeholders
   you can fill from the repo, tell the user it was generated from the default
   template and is marked UNREVIEWED, and ask them to check it. Don't silently
   proceed on defaults, and never invent values in their place.
3. From then on, follow that file. Keep its section headings intact — this skill
   and its references point at them by number/name.

**Precedence:** the project's layout file > this skill > `powerbi-report-author
validate`; where the validator disagrees, the layout file wins and the
disagreement is recorded in its section 10 so it isn't "corrected" later. A
formatting decision the file doesn't cover: ask, then write the answer into it.

## Step 0b — before you reach for a tool, check you have it

The tools below are assumed, not installed by this skill, and a missing one used
to surface as `command not found` in the middle of an edit — several steps after
the point where it could still have been planned around. So the first time a task
is going to use `te`, `powerbi-report-author`, the Desktop bridge or the Modeling
MCP:

```bash
python3 <skill-dir>/scripts/preflight.py     # or: doctor.py --tools
```

It prints each tool as found (with its version) or missing, then what stops
working without it and how to install it. Exit 0 = everything usable on this
platform is present, 1 = something is missing and the report says what that
costs, 2 = not even Python. Two things it is worth reading rather than skimming:

- **Platform.** On Linux and macOS there is no Power BI Desktop, so the bridge
  and every live-model operation are "not available here", not "go install this";
  offline TMDL/PBIR editing, all seven checks and the bulk tools are unaffected.
- **Tabular Editor's expiry.** The tested `te` is an **early preview build that
  stops running on a fixed date**. Once it does, `te format` and offline TMDL
  operations fail with nothing pointing at the cause; preflight reads the date
  out of the banner and warns inside 30 days. The fix is a newer build from
  <https://tabulareditor.com/downloads>.

Pure offline work — editing files, running the checkers — needs none of this and
should not wait on it.

## Machine-wide tools (prerequisites)

Assumed already installed (this skill uses, doesn't install them):

- **Tabular Editor CLI** — `te` on PATH (Linux build) for **offline** TMDL editing.
  Inspect with `ls`/`get`/`find`/`deps`, edit with `set`/`add`/`mv`/`rm`/`replace`,
  plus `bpa`, `validate`, `format`, `diff`, `script`; model via `-m <path>`, useful
  flags `--output-format json|csv|tmdl` and `--non-interactive`. **`--save` against
  the project destroys the PBIP folder layout** — read
  `references/tmdl-and-model.md` before running it. The tested build is an **early
  preview with an expiry date**; when it passes, `te` stops working entirely —
  `preflight.py` reports the date.
- **Tabular Editor Windows build** — `te.exe` at a Windows path (WSL form
  `/mnt/c/Users/<you>/te.exe`) for **live** Analysis Services work; the Linux `te`
  cannot do it. `references/desktop-bridge.md`.
- **PBIR authoring CLI** — `powerbi-report-author` (Microsoft
  `@microsoft/powerbi-report-authoring-cli`). `preview-visuals` / `preview-pages` /
  `preview-filters` / `preview-themes` navigate granular JSON; reading `validate`
  output is `references/themes-and-validate.md`.
- **Desktop bridge** — `powerbi-desktop` (Microsoft
  `@microsoft/powerbi-desktop-bridge-cli`), **Windows-only**; always drive it as
  `powershell.exe -NoProfile -Command "powerbi-desktop <cmd>"`, never straight from
  WSL. Why, and every failure mode: `references/desktop-bridge.md`.
- **Power BI Modeling MCP** (optional) — the better path for editing a **live**
  model when it is registered. `references/modeling-mcp.md`.

If a tool is missing, tell the user which one — `preflight.py` names it, says what
it blocks and how to install it — and stop rather than improvising. Say what still
works, so the answer is "these three parts of the task can go ahead", not just
"no".

## Safe edit protocol (Desktop open vs closed)

Power BI Desktop owns the model in memory while a report is open and **rewrites the
files on save**, silently clobbering external edits. So **before any edit, ask
whether that specific model/report is closed** — per target, since one report can
be open while another is not — and verify rather than assume (`powerbi-desktop
status` → `not_connected`). If it is open, drive the bridge loop instead
(`status` → `hasUnsavedChanges: false` → edit → `reload` → `screenshot`), one
driver at a time. Note that **`reload` re-reads the report layer only**, so TMDL
changes never reach a running Desktop that way. Mechanics, the XMLA push
alternative and the failure modes: `references/desktop-bridge.md`.

## Editing rules

- Keep changes minimal and scoped — match existing naming, formatting, structure.
  Don't reformat or reorder untouched definitions.
- **Match the files' line endings.** PBIR JSON and TMDL written by Desktop are
  **CRLF**, and the JSON files have **no trailing newline**; `file` reports them as
  plain "JSON text data", so nothing warns you. Writing LF turns a one-line change
  into a whole-file rewrite that hides the real diff, and the next Desktop save
  flips it back for another full-file churn. Write with
  `json.dumps(obj, ensure_ascii=False, indent=2).replace("\n", "\r\n")` into
  `open(..., newline="")` with no trailing `\n`; TMDL via `open(..., newline="\r\n")`.
  Verify with `git diff --stat` immediately after writing — more than a handful of
  changed lines for a small edit means the endings are wrong.
- Column/measure naming should match the project's analyst-facing dbt reporting
  layer (the renamed/localized columns).
- **Every measure you add or touch gets a `///` description** saying what it
  means, not what the DAX does — a missing one is a hole in the help page users
  read, not just in a tooltip. Shape and anti-patterns in
  `references/tmdl-and-model.md`, the catalog that surfaces them in
  `references/measure-catalog.md`, language and coverage in section 6 of the
  project's layout file.
- **Comparison series get a deliberate color, and you ask first.** Any chart with a
  previous-period series (PY/PQ/PW/PP/LY/MoM) or a target: ask before applying the
  project's comparison color, and take the value from the model's color measure.
  Where that value comes from, and what to do when the measure doesn't exist yet:
  `references/pbir-visuals.md`.
- **Name every visual so the Selection pane is readable** — including title-hidden
  visuals and visual groups, which otherwise show as bare `Card` / `Group`.
  Mechanics in `references/pbir-visuals.md`; wording and language are section 6 of
  the project's layout file.
- Don't rename or move semantic-model objects without checking they aren't
  referenced elsewhere (visuals, filters, bookmarks) — `te deps` / grep the report.
- Validate JSON/TMDL stays well-formed so the project still opens in Desktop.

## Before you commit

Structural checks over the **whole repo**, not just the files you touched. The
scripts sit beside this file, i.e. `<skill-dir>` below is this SKILL.md's own
directory — in plugin context `${CLAUDE_PLUGIN_ROOT}/skills/powerbi-report-editing`:

```bash
python3 <skill-dir>/scripts/doctor.py [repo-root]     # runs every check, one report
git diff --stat                                       # line endings
```

`doctor.py` is the single habit. It exits 1 only on a real defect — broken
projections or broken M escaping — and 2 when it found no model or report at all
(the path is wrong, the repo is not clean); coverage, naming, theme drift and
theme overrides are reported as backlog and never fail the run. The seven checks
it wraps (`check-visual-projections.py`, `check-m-escaping.py`,
`check-layout-file.py`, `check-measure-descriptions.py`,
`measure-catalog.py --check`, `check-theme-drift.py`, `find-theme-overrides.py`)
still run standalone when you want one with its own flags. All of them, and every
bulk tool, honor `.powerbi-scan-ignore` in the repo root — one path prefix per
line, `#` comments. None of the seven shells out to an external tool, so a failing
check is never a missing `te` — the tool question is its own mode,
`doctor.py --tools` (step 0b).

**Then actually look at it.** Screenshot the page through the Desktop bridge, or
ask the user for one, and confirm the visual renders every field you put in it. A
visual showing one column out of five passes every structural check there is.

Having read the gotchas is not the check. The class of bug these scripts catch has
recurred **on the same day, with the note already in context** — it only stops
being a risk when the check runs as a tool call before the commit.

## Delegating and working in parallel

Check this table at the start of a task, not after doing the work by hand. Any row
that matches → delegate to a subagent on a cheaper/faster model, and send
independent units as parallel agents in one message.

| Trigger | What to ask for back |
|---|---|
| Reading a file >500 lines you only need values out of — `reportThemeSchema-*.json`, a `.dc.html` mockup, a big `visual.json` | **only the values**, never the file |
| Bulk edits across more than ~5 `visual.json` files (repositioning, renames, stripping objects) | a diff summary + the checker's exit code |
| Hunting a reference example ("a Desktop-made `pivotTable` with a hierarchy well") across reports on disk | the path plus the relevant JSON fragment |
| Measuring an existing grid across a repo's pages | the numbers, as a table |

**Keep in the main context**, because a subagent's summary of judgment is
worthless: reading screenshots and deciding whether the page looks right, choosing
values, deviating from the layout file, editing the layout file itself, and the
final verification run before committing. A subagent also cannot speed up the
Desktop reload+screenshot cycle — batching more changes into one round does.
