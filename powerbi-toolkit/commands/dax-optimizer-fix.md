---
description: Work through issues from a DAX Optimizer report — propose, approve (per rule or per issue), apply to TMDL, verify before/after against Desktop, commit, log
argument-hint: [report file or model slug] [issue numbers, ranges or rule ids]
allowed-tools: Bash(python3:*), Bash(powershell.exe:*), Bash(te:*), Bash(git status:*), Bash(git diff:*), Bash(git add:*), Bash(git commit:*), Bash(git checkout:*), Bash(git log:*), Bash(ls:*), Read, Edit
---

Fix DAX Optimizer findings from a report written by
`/powerbi-toolkit:dax-optimizer-report`. The skill that owns the mechanics is
`${CLAUDE_PLUGIN_ROOT}/skills/dax-optimizer-fix/SKILL.md` — read it and follow
its protocol; this command fixes the order and the things people skip.

`$ARGUMENTS`: an optional report (file name or model slug; none = the newest in
`docs/dax-optimizer/`, say which) followed by optional issue numbers, ranges or
rule ids (none = every issue still open in the fix log).

1. **Select** with `daxopt-select.py` and show the candidates grouped by rule,
   with what the fix log already says about them.
2. **Plan** from `references/fix-playbook.md`: class per rule, a diff per issue,
   the traps that apply, the `--by` columns for verification. Ask about
   business meaning you cannot derive; do not guess.
3. **Approve** — mechanical rules as one batch per rule, judgment rules one
   issue at a time. The user may override for this run only.
4. **Baseline** with `daxopt-verify.py baseline` while Desktop has the report
   open and saved. No Desktop on this platform → record `proposed` in the fix
   log and stop.
5. **Desktop closed** (`powerbi-desktop status` → `not_connected`), then
   **apply** the approved diffs to TMDL by the report-editing skill's rules,
   `te format`, `te validate`, `git diff --stat`.
6. **Compare** after `powerbi-desktop open`: equal → continue; a difference →
   revert that measure unless the user explicitly accepts it and the note says
   so.
7. **Commit per rule**, touched TMDL files only, `perf(<model>): …` message; then
   `daxopt-fixlog.py … set … --status fixed --verified equal --commit <sha>`.
   Commit the fix log with the last batch.
8. **Summarise**: applied, skipped, awaiting a decision, the fix log path.

If `${CLAUDE_PLUGIN_ROOT}` is not set, the same files sit in the checkout under
`powerbi-toolkit/skills/dax-optimizer-fix/`.
