# Bulk tools — fixing a backlog, not one visual

The scripts run anywhere, but the two preconditions below — "the report is closed
in Desktop" and the screenshot afterwards — need **Power BI Desktop on Windows**
(or WSL2 with access to a Windows Desktop install); on Linux or macOS neither
check is available.

Two scripts that write rather than report. Both are dry-run by default and both
honor `.powerbi-scan-ignore`, so archived report folders stay untouched. (A third
writer, `measure-catalog.py`, follows the same rules but touches the semantic
model rather than the report — it has its own reference,
`measure-catalog.md`, and the same "run it on one model first" caution applies.)

Neither is a substitute for judgement: they produce a large, mechanical diff that
you must read before committing, and a screenshot afterwards.

## `name-visuals.py` — give every visual a Selection-pane name

```bash
python3 <skill-dir>/scripts/name-visuals.py <repo> [--apply] [--lang en|cs]
```

Derives a name from the visual type and the fields it actually shows — *"Revenue
by division — column chart"*, *"Slicer: period"*, *"# terminations, # closed —
KPI cards"* — and writes it to `visualContainerObjects.title.properties.text`
with `show: false`, which is what a Selection-pane rename in Desktop produces.

- Never renames a visual that already has a title text.
- Reuses an existing title card instead of adding a second one. A duplicate
  `"title"` key parses (last wins) and would silently discard the new name, so
  every edit is parsed back and the name re-read before the file is written.

**Float literals are the trap.** Desktop writes positions like
`78.553615960099748`; Python's shortest round-trip is `78.55361596009975`, so a
naive `json.load`/`json.dump` rewrites numbers across the whole file and buries
the real change. The script masks every float literal with a placeholder before
parsing and restores it after dumping, then refuses the file outright if the
unmodified round-trip is not byte-identical.

Expect roughly +19 lines per touched file and nothing removed. Anything else in
`git diff --numstat` means something went wrong.

## `backfill-dax-blocks.py` — the `---` half of a measure description

```bash
python3 <skill-dir>/scripts/backfill-dax-blocks.py <repo> [--apply] [--format]
```

Copies each measure's own DAX into its `///` description after a `---`
separator, because a thin report cannot see the model's definitions and the
description is the only place the formula reaches the report author. `--format`
runs each expression through `te format -e` first — short lines, which is te's
default; `--long` is the opt-in and we don't use it.

- Only touches measures that **already have prose**. A DAX block with no
  explanation above it is noise; write the sentence first, then re-run.
- Never overwrites an existing `---` block.
- Reads with `newline=""` so CRLF survives. Without that, Python translates line
  endings on read, the CRLF detection reports LF, and every line in the file is
  rewritten — which has happened in practice and buried a 2000-line addition in a
  4000-line diff.

Budget about 0.75 s per measure with `--format`; a 2800-measure model is a
background job, not an interactive one.

## Before you run either one

- **The repo must have no unrelated work in progress.** These tools touch
  hundreds of files, and mixing that with someone's half-finished edit makes both
  unreviewable. Check `git status` first; if it is dirty with other people's
  changes, stop.
- **The report must be closed in Desktop** — `powerbi-desktop status` →
  `not_connected` for that file. Desktop rewrites what it owns on save.
- Commit the bulk change on its own, so reverting it is one command.
