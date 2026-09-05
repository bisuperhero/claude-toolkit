---
name: glitchtip-triage
description: Triage and fix the most frequent GlitchTip (Sentry-compatible) error for a project. Use when the user wants to work through GlitchTip or Sentry errors, fix the top error, see what is failing in production, or review unresolved issues, exceptions and stack traces. Also matches Czech prompts such as "co hoří v glitchtipu". Connects via the GlitchTip MCP server, prefers production over dev noise, picks the highest-count unresolved issue, asks how to proceed (fix / already fixed → resolve / skip / add a note), then diagnoses against the repo and proposes a fix. One issue at a time, no edits without approval.
---

# GlitchTip triage

Interactive loop: find the most frequent unresolved error in GlitchTip, ask the
user what to do with it, and (if they want) diagnose it against the repo and
propose a fix. Sentry-compatible — GlitchTip's MCP exposes Sentry-style tools.

## Preflight (before anything else)

- Confirm the project's GlitchTip MCP server is connected — list the MCP tools and
  check for `list_organizations`, `list_projects`, `list_issues`, `get_issue`,
  `get_latest_event`, `get_event`, `update_issue`. If they aren't available, tell
  the user to connect the GlitchTip MCP (endpoint `https://<glitchtip>/mcp`,
  `GLITCHTIP_ENABLE_MCP=True`) and stop — don't guess at errors without it.
- The GlitchTip project name is in the repo's `CLAUDE.md` (Production section). If
  several projects exist, use that name to pick; otherwise ask which one.

## Loop (one issue per round)

### 1. Find the top error

- Resolve the org/project: `list_organizations` → `list_projects` (match the org +
  project from CLAUDE.md).
- **Prioritize production.** Error *volume* is usually dominated by dev noise
  (PK warnings, metadata-DB errors), but prod issues are the ones that matter.
  Filter to production first — `list_issues` with `query='is:unresolved'` plus an
  environment / `server_name` filter for prod (the prod tag value is in CLAUDE.md,
  e.g. `{{ProjectName}}Mage` vs dev `{{ProjectName}}MageDev`). Only fall back to
  dev issues if prod is clean or the user asks.
- Sort the filtered issues by event count descending; take the top one not already
  handled this session.
- If there are no unresolved prod issues, say so (and offer to look at dev) before
  stopping.

### 2. Present it concisely

Show, in a few lines:
- Title / exception type and culprit (file:function if available).
- Event count and last-seen time.
- One-line "likely area" guess based on the title.

Then pull `get_latest_event` (or `get_event`) to have the stack trace ready, but
don't dump the whole thing yet — summarize the top frames.

### 3. Ask how to proceed

Use the AskUserQuestion tool with these options — **always offer all four**:

- **Yes — diagnose and propose a fix** — go to step 4.
- **Already fixed — resolve it** — the fix is already in the code, just never
  closed in GlitchTip. Call `update_issue(status="resolved")` right away (this
  answer *is* the OK — don't ask again), then go back to step 1 for the next issue.
- **No — skip for now** — skip this issue, leave it unresolved, next issue.
- **Add a note** — the user types free-form context, e.g.
  - "watch out for X / the cause is probably Y" → fold that hint into the
    diagnosis and proceed as if "Yes", weighting the user's note.
  - anything implying it's already fixed → treat it as "Already fixed".

Always honor the note's intent before doing your own analysis.

**Why "Already fixed" matters:** stale issues (last seen weeks/months ago, or a
`release` tag well behind HEAD) are very often already fixed in the repo and only
left open in GlitchTip. The older the issue, the more likely this is — lead with
this option, and say in the question why you suspect it (e.g. "last seen 5 Aug,
release <sha>").

### 4. Diagnose (on "Yes" or an actionable note)

- Read the full latest event: stack trace, culprit, breadcrumbs, tags
  (environment, release), and any captured variables.
- Locate the implicated code in the repo (search for the culprit file/function and
  the error message). Read enough surrounding code to understand the cause.
- Explain the root cause in plain terms: what triggers it, why it throws.

### 5. Propose a fix

- Present the proposed change (diff-style or clear before/after) and the reasoning.
- **Do not apply it without approval.** Wait for the user to confirm.
- On approval, make the edit. Suggest a commit following `COMMIT-STANDARD.md`
  (e.g. `fix(loader): guard against null DOCDATE`).
- Mention any verification step (rerun the block, a dbt test, a query via toolbox).

### 6. Close out

- Ask whether to mark the issue resolved in GlitchTip. On yes, `update_issue`
  with status `resolved`, then report the issue id and its new status back.
- If the fix is committed but not yet deployed, leave the issue open and say so.
  Resolving before the release lands hides a regression that is still live.
- Note anything worth carrying forward — a recurring cause, a fragile source, a
  source system that fails predictably — so the next triage starts warmer.
- Stop here. One issue per run; do not roll straight into the next one.
