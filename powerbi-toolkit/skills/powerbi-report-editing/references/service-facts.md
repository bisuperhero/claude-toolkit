# Power BI Service facts — keep them in one file, not in your head

Workspace IDs, dataset IDs, which report is thin vs. thick, where the REST API
credentials live, what's automated vs. manual — none of this is in the repo's
report files. It lives in the Service, in a `.env` somewhere, in whoever set up
the refresh pipeline. Every time it's needed it gets re-discovered: a workspace
GUID copied out of a browser URL, a dataset name grepped out of a thin report's
`definition.pbir`, a "wait, which env var was it again" search through a Mage
project. That's real time lost to something that is a dozen static facts.

**Fix: one file per project, `POWERBI-SERVICE.md`, beside the reports.** Same
idea as `POWERBI-LAYOUT.md` (`layout-standard-template.md`) — a project-specific
file this skill does not hold values for, generated once and kept current by
whoever touches the Service setup next.

This skill does not auto-generate `POWERBI-SERVICE.md` the way it does the
layout file — Service facts aren't needed for most editing tasks, only look for
it when a task actually needs one of these facts (setting up a refresh, checking
whether a report is thin, finding which dataset backs a report). If it's missing
and the task needs it, create it from the template below and fill in what you can
verify; mark anything you couldn't confirm as such instead of guessing.

## Template

Copy this into the reports repo as `POWERBI-SERVICE.md` and fill in the fields.
Leave a field explicitly marked `unknown` rather than deleting it — a missing
row looks like "nobody checked", an `unknown` row looks like "checked, not
knowable from here".

```markdown
# Power BI Service facts — {{PROJECT_NAME}}

Status: **UNREVIEWED** — filled in from what could be verified on
{{DATE}}; confirm workspace/dataset IDs against the Service before relying on them.

## Workspace

- Name: `{{workspace name}}`
- ID: `{{workspace GUID}}`

## Datasets

| Dataset | ID | Backs report(s) |
|---|---|---|
| {{name}} | {{GUID or "unknown"}} | {{report name}} |

## Report connection type

| Report | Type | Notes |
|---|---|---|
| {{name}} | thin (`byConnection`) / thick (`byPath` / own `.SemanticModel`) | |

## REST API credentials

- Where: `{{env var names}}` in `{{path to .env, never committed}}`
- **Never write the actual secret values into this file.**

## Automation

- Automated: {{e.g. refresh via Mage pipeline, file/module}}
- Manual: {{e.g. publishing reports from Desktop}}

## Legacy / excluded folders

- `{{folder}}` — {{why it's excluded from checks}}
```

## Three shapes to fill in

Three recurring project shapes, written as skeletons rather than data: every GUID
is a `{{placeholder}}` you replace with the value you verified. What is worth
copying is the **set of facts each shape needs recorded**, not the values —
which project you have determines which of the three you write.

### Shape A — one workspace, one dataset, automated refresh

- Workspace: name plus ID `{{workspace-a-id}}`.
- One dataset, backing every report in the repo — so the "which dataset backs
  this report" column of the template is a formality and can say "all".
- Service principal credentials in `AZURE_TENANT_ID` / `AZURE_CLIENT_ID` /
  `AZURE_CLIENT_SECRET`, in the `.env` of the extraction repo.
- Refresh automated from a pipeline in the extraction repo (record the module
  paths); report publishing is manual, from Desktop.
- Legacy/archive folder `{{legacy-folder}}/` — exclude from checks.

### Shape B — one workspace, several datasets

- Workspace: name plus ID `{{workspace-b-id}}` — a **different** workspace from
  shape A, and the whole point of writing the ID down.
- Several datasets, typically including a second copy of the main model with RLS
  applied. Here the per-report dataset mapping is real information: fill in one
  row per report, with the dataset ID, or the wrong model gets refreshed.
- Same credential/automation mechanism as shape A: it lives in the extraction
  repo, not in the reports repo.

### Shape C — no API integration

- No API integration, no service principal. Publishing and any refresh work is
  fully manual from Desktop — record that fact itself and leave the credential and
  automation sections marked `unknown`/`n/a` rather than deleting them.

## What Power BI Pro cannot tell you

Verified 2026-08-31 against a live workspace. Don't assume the REST API can
answer "did someone change this report in the Service" — on a Pro-only tenant
it can't, and the following is why, concretely:

| Question | Can Pro answer it? | Detail |
|---|---|---|
| Report metadata (`GET /v1.0/myorg/groups/{ws}/reports`) | Partial | Returns only `datasetId`, `datasetWorkspaceId`, `embedUrl`, `format`, `id`, `isFromPbix`, `isOwnedByMe`, `name`, `reportType`, `subscriptions`, `users`, `webUrl` — **no last-modified time, no author.** |
| "Was this dataset republished recently?" | No | Datasets carry `createdDate`, but it does **not** change on republish — useless as a change signal. |
| Last-modified time for a report or dataset | Only admin-scoped | Available from Scanner API or activity events, both of which require admin/tenant-level API access, not the per-workspace REST API a report editor normally has. |
| Live model introspection (XMLA endpoint) | No | XMLA is Premium/PPU/Fabric only; not available on Pro. |
| PBIR vs. legacy report format | Yes | The `format` field on the report metadata distinguishes `PBIR` from `PBIRLegacy`. |

**Conclusion:** on Power BI Pro there is no reliable way to answer "did someone
edit this report in the Service since I last touched it" via the REST API — no
endpoint returns a modification timestamp at the workspace-API scope. The only
way to actually inspect current content is `Export Report In Group`, and for a
**thick** report that downloads the full semantic model along with it — for a
large model that runs for tens of minutes. It's practical only for **thin**
reports (no embedded model to pull) or genuinely small thick ones. Don't build a
"check if the Service copy changed" step around Pro API polling; if that
guarantee matters, it has to come from a process rule (only publish from one
place, note publishes in `POWERBI-SERVICE.md`) rather than from the API.
