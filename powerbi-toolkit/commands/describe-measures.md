---
description: Write the missing measure descriptions in a model and backfill their DAX blocks
argument-hint: [part of a model or table name]
allowed-tools: Bash(python3:*), Bash(git status:*), Bash(git diff:*), Bash(te:*), Bash(powershell.exe:*), Read, Edit
---

Close the gap in measure descriptions. A `///` block is the measure's Data-pane
tooltip, the only place a thin report can see the formula at all, and — since the
measure catalog exists — the text users read on the report's help page. A measure
with no description is a hole in all three.

**Read first, before writing a single line:** the "Measure descriptions" section
of `${CLAUDE_PLUGIN_ROOT}/skills/powerbi-report-editing/references/tmdl-and-model.md`
(shape, the two anti-patterns, the ≤160-character target) and section 6 of the
project's layout file (language and coverage — this is per project, do not guess
the language from the model's culture).

## Order of work

1. **The backlog.** `check-measure-descriptions.py <repo> --list`, narrowed to
   `$1` when an argument was given. Report the counts before starting: how many
   have no description, how many have prose but no `---` block, how many hit an
   anti-pattern.
2. **Desktop closed** for the model being edited —
   `powershell.exe -NoProfile -Command "powerbi-desktop status"` → `not_connected`.
   Desktop rewrites the model on save and will clobber this.
3. **Write the prose**, table by table, to the shape and the two anti-patterns in
   the reference you just read. One thing it does not say, and this command does:
   **do not invent semantics.** If the DAX is ambiguous, or the business meaning is
   not derivable from the model and the dbt reporting layer, ask. A confident wrong
   description is worse than none now that it shows on a user-facing help page.
4. **Parallelize by table.** Tables are independent, so send one subagent per
   table in a single message with the convention, the anti-patterns and the
   project's language spelled out in the prompt, and have each return **the
   proposed descriptions as text, not file edits**. Review them yourself before
   they land — this is judgment, and a subagent's summary of judgment is
   worthless. Keep small tables and anything you are unsure about in the main
   session.
5. **Backfill the formulas** once the prose is in:
   `backfill-dax-blocks.py <repo> --apply --format`. It only touches measures that
   already have prose and never overwrites an existing `---` block. Budget ~0.75 s
   per measure with `--format`, so on a model with hundreds of measures run it in
   the background rather than waiting on it.
6. **Verify.** Re-run the checker for the new numbers, run
   `doctor.py`, and check `git diff --stat` — TMDL is CRLF, and a whole-file
   rewrite means something wrote LF.

## Two things worth saying to the user

- **The `---` DAX block is not padding.** In a thin report the model is published
  and the report author cannot see a measure's definition at all; the description
  is the only place the formula exists. It is also how the formula reaches the
  help page, because `INFO.VIEW.MEASURES()[Expression]` returns blank for anyone
  without write permission on the model.
- **The block is a copy and goes stale.** Whenever a measure's DAX changes, its
  `---` block changes in the same edit.

Commit the descriptions on their own, separately from any bulk backfill.

If `${CLAUDE_PLUGIN_ROOT}` is not set, the same files sit in the checkout under
`powerbi-toolkit/skills/powerbi-report-editing/`.
