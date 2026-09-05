---
description: Run every Power BI structural check over the repo and triage what it finds
argument-hint: [repo path]
allowed-tools: Bash(python3:*), Bash(git status:*), Bash(git diff:*), Bash(te:*), Read, Edit
---

Run the pre-commit checks over the **whole** repo and act on the result. Run it as
a tool call, not as a reminder — the "Before you commit" section of
`${CLAUDE_PLUGIN_ROOT}/skills/powerbi-report-editing/SKILL.md` says why, and which
seven checks this wraps.

`$ARGUMENTS` is the repo path to scan; with no argument, use `.`:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/powerbi-report-editing/scripts/doctor.py $ARGUMENTS
```

Then:

1. **Blocking findings** (exit 1 — broken visual projections, broken M escaping)
   are real defects and stop the commit. Re-run that single check with its own
   flags for the detail, fix the **actual defect** in the file, and run doctor
   again. Never make a check pass by loosening the check. What a correct
   projection looks like is in `references/pbir-visuals.md`; the M escaping
   invariant — a quote inside `Value.NativeQuery` left undoubled makes Desktop
   refuse to open the **entire project** — is in `references/tmdl-and-model.md`.
2. **Backlog findings** (naming, description coverage, missing measure catalog,
   theme drift, theme overrides) never block. Report them, say roughly how big
   each one is, and **ask before fixing** — several have dedicated tools that
   produce a large mechanical diff of their own (`name-visuals.py`,
   `backfill-dax-blocks.py`, `measure-catalog.py`) and each belongs in its own
   commit.
3. **Line endings.** `git diff --stat`, read against the CRLF rule in the skill's
   editing rules. More than a handful of changed lines for a small edit means
   something wrote LF and rewrote the whole file; fix it before committing.
4. **Say the last part out loud.** Structural checks passing is not the same as
   the report looking right. A visual showing one column out of five passes every
   check there is. If pages were changed, screenshot them through the Desktop
   bridge or ask the user for one.

**Exit 2 is not a green run.** `doctor.py` returns 2 and reports that it found no
model or report — the path is wrong, not the repo clean. Say so.

If `${CLAUDE_PLUGIN_ROOT}` is not set, the same files sit in the checkout under
`powerbi-toolkit/skills/powerbi-report-editing/`.
