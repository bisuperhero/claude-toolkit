---
name: dax-optimizer-fix
description: "Work through the issues in a DAX Optimizer report produced by dax-optimizer-report: pick a report (or the newest one) and some or all of its numbered issues, propose a DAX rewrite per issue from the rule playbook and the public knowledge base, get approval — mechanical rules as one batch per rule, judgment rules one change at a time — apply the change to the TMDL in the repo with Desktop closed, prove the measure still returns the same values with a before/after comparison against Desktop, commit per rule, and record every outcome in the report's fix log. Use when asked to fix, apply, implement or work through DAX Optimizer findings, issues, recommendations or a specific issue number or rule from such a report."
---

# DAX Optimizer fix

Turn the findings of a `dax-optimizer-report` run into approved, verified,
committed DAX changes. The report is the contract: issues are addressed by
their number in a named report, matched by fingerprint, and every outcome lands
in that report's fix log.

Three things this skill never does: apply a change nobody approved, keep a
change whose before/after comparison differs without the user explicitly
accepting the difference, and touch a model while Desktop has it open.

| Doing this | Read first |
|---|---|
| Deciding what a rule means and what its rewrite looks like | `references/fix-playbook.md` (one entry per rule, with the traps) |
| Proving a rewrite returns the same numbers | `references/verification.md` |
| Editing TMDL, `te format` / `te validate`, CRLF, `///` descriptions | the `powerbi-report-editing` skill, `references/tmdl-and-model.md` |
| Opening, reloading or closing Desktop through the bridge | the `powerbi-report-editing` skill, `references/desktop-bridge.md` |

Scripts (in `scripts/`, stdlib Python 3.8+):

| Script | Job |
|---|---|
| `daxopt-select.py [REPORT] [--issues 3,7,12-15] [--rules 100200] [--measure x] [--format json\|md]` | picks the report (newest in `docs/dax-optimizer/` when none is named), parses it, filters, emits the issues with DAX, span, fingerprints and TMDL location |
| `daxopt-verify.py discover\|baseline\|compare` | captures measure values from a running Desktop before the change, re-queries after, diffs |
| `daxopt-fixlog.py REPORT set 3,7 --status fixed --verified equal --commit <sha>` | upserts rows in `<report>_fixes.md`; `show` prints it |

## Inputs

- **Which report.** The user names a file (`2026-01-05_1420_sales.md`), a model
  slug, or nothing. Nothing = the newest report by file name in
  `docs/dax-optimizer/`; say which one you picked before doing anything.
- **Which issues.** Numbers, ranges, rule ids, a measure name, or nothing =
  everything still open in the fix log. Numbers are only meaningful inside the
  named report — a later report renumbers; fingerprints do not change.
- **Project facts** from the project's `CLAUDE.md`: reports folder, the Date
  table and the dimension columns a measure is usually sliced by (for
  `--by`), the language of `///` descriptions (layout file, section 6).

## Protocol

Stop at the first step that does not hold and say which one.

1. **Select.** `daxopt-select.py <report> [filters] --format md` → the
   candidate list, grouped by rule. Cross it with the fix log: issues already
   `fixed`, `ignored` or `skipped` are shown as such and left out unless the
   user names them explicitly.
2. **Classify and plan.** For every rule in the selection read its playbook
   entry. Produce the plan the user approves against: per rule, its class
   (mechanical or judgment), the issues under it, and for each issue the
   proposed rewrite as a diff of the measure's DAX, the trap(s) from the
   playbook that apply to this measure, and the `--by` columns the
   verification will use. Summarise the KB article in your own words when it
   helps; never paste it.
   - If the DAX depends on business meaning you cannot derive (what a BLANK
     means here, whether ties matter), say so in the plan and ask — a
     confident wrong rewrite is worse than an open question.
   - A measure that appears under several rules gets one combined rewrite,
     listed under the rule with the highest relevance.
3. **Approve.** Hybrid, per rule:
   - **mechanical** rules: present the batch (all diffs), ask once per rule,
     apply the batch on a yes;
   - **judgment** rules: ask per issue, apply one at a time.
   The user can override for the run ("apply everything", "one by one") —
   honour that for the run only, never remember it. No approval, no edit.
4. **Baseline** (Desktop must be open with the report, `hasUnsavedChanges:
   false`): `daxopt-verify.py baseline --pbip <Report>.pbip --out
   <cache>/verify/<run>-<rule>-before.json --measure … --by …` for every
   measure the approved batch touches, plus every measure that references
   them directly (the report's reach column says how many; the fix log notes
   the names). Without a Desktop on this platform: propose, record the
   proposals as `proposed` in the fix log, and stop — do not apply.
5. **Close Desktop** (ask the user; the bridge cannot close it), confirm with
   `powerbi-desktop status` → `not_connected`.
6. **Apply** the approved diffs to the TMDL files by the other skill's
   editing rules: minimal change, CRLF preserved, the `///` description
   updated when the meaning of the code changed, `te format` on the touched
   measures, `te validate`. `git diff --stat` must show only the touched
   measure definitions.
7. **Compare.** `powerbi-desktop open <Report>.pbip`, wait for `status` →
   connected, then `daxopt-verify.py compare --baseline … --out …-after.json`.
   - exit 0: equal → go on.
   - exit 1: a difference → show the table. Default is **revert that
     measure** (git checkout of its file, re-run compare). Keep it only if
     the user reads the difference and explicitly accepts it — record the
     acceptance in the fix log note.
   - exit 2: could not query → fix the cause (Desktop not up, wrong catalog),
     do not proceed on a guess.
8. **Commit per rule.** Stage only the touched TMDL files. Message:
   `perf(<model>): <rule title> in <n> measure(s) (DAX Optimizer <docId>)`,
   body listing the measures and the verification result. Then
   `daxopt-fixlog.py <report> set <numbers> --status fixed --verified equal
   --commit <sha>`; skipped ones `--status skipped --note "<why>"`, user
   rejections `--status ignored`. Commit the fix log with the last batch.
9. **Report back.** What was applied, what was skipped and why, what still
   needs a decision. Point at the fix log. Suggest the next
   `dax-optimizer-report` run only when the user asks whether the fixes
   registered — it costs a licence run.

## Rules that are easy to break

- **Numbers belong to one report.** Never carry issue numbers from an older
  report; re-select against the report the user named.
- **The playbook decides the class, not the size of the diff.** A one-line
  change to a context transition is still judgment.
- **Reach is blast radius.** A measure referenced by 40 others is verified
  through those others too, or the batch is split.
- **Never "fix" by loosening the verification.** A tolerance is for
  floating-point noise, not for a 0.3 % difference.
- **Desktop owns the files while it is open.** Editing TMDL with the report
  open is silently undone on the next save.
- **Nothing client-specific into this plugin.** Examples in the playbook are
  generic on purpose.

## Delegating

The plan and every approval stay in the main context. What can go to a
subagent: reading a long measure's dependency chain (`te deps`) and returning
the names, and running `daxopt-verify.py` over many measures and returning the
diff table. Nothing that decides.
