---
description: Build or refresh the measure catalog (INFO.VIEW.MEASURES) in a semantic model, then verify it in Desktop
argument-hint: [part of a model name]
allowed-tools: Bash(python3:*), Bash(git status:*), Bash(git diff:*), Bash(git log:*), Bash(powershell.exe:*), Read
---

Build the measure catalog in this repo's semantic model(s): the measure-holder
table (`.Measures` / `00 MEASURES`) derives itself from `INFO.VIEW.MEASURES()`,
so a report help page can list every measure with the table it lives in and its
description. Read `${CLAUDE_PLUGIN_ROOT}/skills/powerbi-report-editing/references/measure-catalog.md`
before doing anything — the reasoning and every gotcha are there.

`$1`, when given, is a substring of the model name; pass it to `--only` so a
first run touches one model. With no argument, run the dry run over the whole
repo and ask which model to start with — do not apply to every model on the
first pass.

Script: `${CLAUDE_PLUGIN_ROOT}/skills/powerbi-report-editing/scripts/measure-catalog.py`

Work in this order and stop at the first thing that does not hold:

1. **Clean tree.** `git status --short`. Other people's half-finished work must
   not be mixed into this diff; if it is dirty with unrelated changes, say so and
   stop.
2. **Dry run** the script over the repo (`--only "$1"` when an argument was
   given). Show the user what it would change.
3. **Desktop must be closed for that model.** Check with
   `powershell.exe -NoProfile -Command "powerbi-desktop status"` and expect
   `not_connected`. If it is open, stop and ask — Desktop rewrites the files it
   owns on save and will clobber this.
4. **Language.** Column names follow section 6 of the project's layout file
   (`POWERBI-LAYOUT.md` or the CLAUDE.md section). Czech project → default;
   English model → `--lang en`. If the layout file does not say, ask.
5. **Apply**, then `git diff --stat`. Expect roughly 48 added / 7 removed lines
   in one table file per model. Anything larger means line endings went wrong —
   investigate before going further.
6. **If the script refused** because reports still bind a column it would drop,
   do not force it. Re-run for that model with
   `--create '<name>'` so the catalog lands in its own table and the holder is
   left alone.
7. **Verify for real.** Tell the user to open that model in Desktop and refresh
   it, and to confirm in the data view that the table has one row per measure and
   that `Popis`/`Description` is populated. This is the only check that catches
   the two things nothing offline can: a circular dependency, and whether the
   line breaks in a `///` block survive into the column. Offer a bridge
   screenshot if Desktop is already driving.
8. **Report the state**: run the script with `--check`, and mention any model
   still without a catalog.

Do not commit on the user's behalf unless they ask. When they do, the model
change goes in its own commit.

Two things to say out loud if they come up, because they are surprising:

- The catalog deliberately does not use `INFO.VIEW.MEASURES()[Expression]` — that
  column is blank for anyone without write permission on the model. The formula
  reaches the help page through the `---` block in the measure's description
  instead.
- After publishing, the Service needs **one more refresh** before new measures
  appear in the catalog. Publishing alone does not recalculate it.

If `${CLAUDE_PLUGIN_ROOT}` is not set, the same files sit in the checkout under
`powerbi-toolkit/skills/powerbi-report-editing/`.
