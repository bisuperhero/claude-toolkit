---
name: dax-optimizer-report
description: "Analyze a Power BI semantic model with DAX Optimizer (app.daxoptimizer.com) and write a numbered Markdown report of the DAX performance issues it found — overview tables, one section per issue with the flagged expression, reach, relevance and a knowledge-base link, plus a technical section a later fix pass consumes. Use when asked to run DAX Optimizer, check a model's DAX performance, refresh the DAX issues report, or read a result zip someone else produced. Drives the official `daxoptimizer` CLI with the user's own browser login (no service account), DAX Studio's `dscmd.exe` for VPAX extraction from a running Desktop, and the `daxopt-report.py` renderer. It does not change any DAX — proposing and applying fixes is a separate skill."
---

# DAX Optimizer report

Send a model's VPAX to DAX Optimizer through the **official CLI**, get the
analysis back as JSON, and render it as a report people can read and a fix pass
can act on. The skill **reports; it never edits a measure.**

Every run of the analysis **costs one run of the user's DAX Optimizer licence**
(Desktop licence: 20 per day, 5 active models) and sends the model's metadata
(names, DAX, cardinalities) to Tabular Tools' Azure region. Both are the user's
call, every time — see the protocol.

| Doing this | Read first |
|---|---|
| Logging in, listing models, running `analyze`, reading its output | `references/cli.md` |
| Producing the VPAX (existing file / running Desktop / XMLA), obfuscation | `references/vpax-extraction.md` |
| Understanding `DaxOptimizer.json` and what the report shows | `references/result-json.md` |

## Where things live

- **Tools** — `daxoptimizer` (NuGet `Dax.Optimizer.CLI`) and `dscmd.exe` (DAX
  Studio) on the **Windows side**, called from WSL through
  `powershell.exe -NoProfile -Command "…"`. The preflight of the sibling skill
  reports both: `python3 <plugin>/skills/powerbi-report-editing/scripts/preflight.py`.
  On Linux/macOS without a Windows host only the "existing `.vpax`" source and
  the renderer are available.
- **Per-project facts** in the project's `CLAUDE.md`, section "DAX Optimizer":
  region, workspace id, model id per semantic model, VPAX source
  (`file` / `desktop`), whether uploads are obfuscated. Never in this plugin —
  it is public.
- **Cache** — `.powerbi-cache/dax-optimizer/` in the project (gitignored):
  VPAX files, dictionaries, result zips. A result zip is the only way to read an
  analysis again without paying another run, so keep it.
- **Report** — `docs/dax-optimizer/<YYYY-MM-DD_HHMM>_<model-slug>.md` in the
  project, committed. The script names it itself (`--output-dir`) from the
  analysis run's time, so the folder is a history and the fix skill cites one
  report exactly. It contains DAX excerpts, i.e. nothing the repo does not
  already hold.

## Protocol

Stop at the first step that does not hold and say which one.

1. **Preflight.** Run the preflight script (above). `daxoptimizer` missing →
   the install line is in its output; `dscmd.exe` missing → only the `file`
   source works. Then `daxoptimizer account show`. Not logged in → run
   `daxoptimizer login --region <region from CLAUDE.md>` and **tell the user to
   sign in in the browser window that opens**. The skill never types
   credentials, never asks for them, never reuses another person's token cache.
2. **Which model.** `workspace model list <workspace-id>` when CLAUDE.md does
   not name the model id yet. `isSlotEnabled: false` means the model cannot be
   analysed until a slot is freed in the web app — say so, do not try to create
   a model with the experimental flags.
3. **Is there a fresh result already?** Look in the cache for a zip of this
   model newer than the last change to its `*.SemanticModel/`. If there is one,
   render it (step 6) and skip the run — the user can always ask for a new one.
4. **VPAX.** Per `references/vpax-extraction.md`:
   - `file`: the user names an existing `.vpax`/`.ovpax` (+ `.dict`).
   - `desktop`: `powerbi-desktop status` must show the report open; report
     `hasUnsavedChanges` out loud — a VPAX from an unsaved Desktop describes the
     in-memory model, not what is in git, and the report's metadata must say so.
     Then `dscmd.exe vpax … -s '<Report>.pbip' -d '<GUID>'` (bare file name,
     catalog GUID required).
   - Obfuscate iff the project says so, and then **always** — an obfuscated and
     a plain upload of the same model do not share fingerprints, so mixing modes
     breaks the web app's Fixed/Ignored tracking and any local diff.
5. **Consent, then run.** Say exactly: which model, that it consumes 1 run, and
   that the model's metadata leaves the machine (obfuscated or not). Only after
   a yes: `daxoptimizer analyze <vpax> --workspace-id … --model-id … --output
   <cache>/<model>/<timestamp>.zip`. About a minute. `SucceededWithErrors` is a
   normal outcome — it means some measures could not be parsed and are listed in
   the report's "Not analysed" section, not that the run failed.
6. **Render.**
   ```bash
   python3 <skill-dir>/scripts/daxopt-report.py <result.zip> \
       --output-dir docs/dax-optimizer \
       --model <path>.SemanticModel --title "<model name>" \
       [--dict <file>.dict] \
       --meta source=<vpax file> --meta desktop_unsaved=<true|false>
   ```
   The report is deterministic and named after the run; do not hand-edit or
   rename it. Never invent `--meta` values — omit what you do not know.
7. **Read it back to the user, briefly.** Counts, the top rules by total
   relevance, the two or three issues with the biggest reach, anything in "Not
   analysed". Then stop. **Proposing or applying fixes is the other skill's
   job**; if the user asks for fixes now, say that and hand over the report path
   and the issue numbers they named.

## What the report is for

- **Section 1** (issues by relevance) and **2** (rules) are the two overview
  tables: what to fix first, and which rule to batch fixes by.
- **Section 3** is one numbered section per issue: flagged expression, full DAX
  (once per measure), reach, relevance split into CPU and materialization, KB
  link, TMDL location. Numbers are for humans and change between runs.
- **Section 5** holds the stable ids — the recommendation and measure
  fingerprints — and the run metadata. A later run of the same model in the
  same obfuscation mode can be diffed by fingerprint; the numbers cannot.

Knowledge-base articles (`https://kb.daxoptimizer.com/d/<id>`) are public and
are Tabular Tools' content: link them and summarise in your own words when the
user asks what a rule means; never paste an article into the repo.

## Rules that are easy to break

- **Never run `analyze` without the consent line.** Not for a re-check, not
  because the previous zip looks old.
- **One obfuscation mode per model, forever.** Switching costs the history.
- **`hasUnsavedChanges: true` is a fact for the report, not a blocker** — but
  it must be in the metadata and in what you tell the user.
- **Do not put ids, model names or report files from a client project into this
  plugin.** Examples in the references are anonymised on purpose.
- **A dirty working tree is not a reason to stop** — this skill only writes the
  report and the cache. List what is dirty and go on.

## Delegating

The renderer is a script; there is nothing to delegate in a normal run. Reading
a 2 MB `DaxOptimizer.json` for a few values is a job for a subagent that returns
the values, not the file.
