---
description: Run DAX Optimizer on a semantic model (1 licence run, with consent) and write the numbered issues report to docs/dax-optimizer/
argument-hint: [model name or path to a result .zip]
allowed-tools: Bash(python3:*), Bash(powershell.exe:*), Bash(git status:*), Bash(git diff:*), Bash(ls:*), Bash(mkdir:*), Bash(cp:*), Read
---

Produce the DAX Optimizer report for a model in this repo. The skill that owns
the mechanics is `${CLAUDE_PLUGIN_ROOT}/skills/dax-optimizer-report/SKILL.md` —
read it and follow its protocol; this command only fixes the order and the two
things people forget.

`$ARGUMENTS` is either a substring of the model name (which `*.SemanticModel`
to analyse, and which model id in the project's `CLAUDE.md`) or a path to a
result `.zip` that already exists — in which case skip straight to rendering and
consume no run.

1. **Preflight and login.** Run the preflight script; then
   `powershell.exe -NoProfile -Command "daxoptimizer account show"`. Not logged
   in → `daxoptimizer login --region <region>` and ask the user to finish the
   sign-in in the browser window. You never enter credentials.
2. **Project facts.** Region, workspace id, model id, VPAX source and the
   obfuscation setting come from the "DAX Optimizer" section of the project's
   `CLAUDE.md`. If the section is missing, get the ids with
   `daxoptimizer workspace list` / `workspace model list`, tell the user what
   you found, and ask them to add the section before the first run.
3. **Cache first.** A result zip in `.powerbi-cache/dax-optimizer/<model>/`
   newer than the model's last change is rendered as-is. Say that you did.
4. **VPAX.** `desktop` source: `powerbi-desktop status` must list the report;
   report `hasUnsavedChanges`. `file` source: ask for the path. Obfuscate only if
   the project says so, and then every time.
5. **Consent line, then `analyze`.** "This consumes 1 run on model X and sends
   its metadata (obfuscated: yes/no) to DAX Optimizer — go ahead?" Wait for a
   yes. Save the zip in the cache.
6. **Render** with `daxopt-report.py --output-dir docs/dax-optimizer` (the
   script names the file `<YYYY-MM-DD_HHMM>_<model-slug>.md` after the run),
   with `--model`, `--title`, `--dict` when obfuscated, and `--meta` only for
   facts you actually have (source file, `desktop_unsaved`).
7. **Summarise** in a few lines: counts, top rules, biggest-reach issues,
   anything not analysed. Give the report path. **Do not propose fixes** — that
   is the fix skill's job; if asked, say so and stop.

If `${CLAUDE_PLUGIN_ROOT}` is not set, the same files sit in the checkout under
`powerbi-toolkit/skills/dax-optimizer-report/`.
