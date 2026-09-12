# `daxoptimizer` CLI — install, auth, discovery, analyze

The CLI is Tabular Tools' official, supported, cross-platform .NET tool for
DAX Optimizer (NuGet `Dax.Optimizer.CLI`). It uploads a VPAX, runs the
analysis in the Tabular Tools service, and downloads the full result as JSON.
No scraping, no shared credentials — every user authenticates as themselves.

## Install

```bash
dotnet tool install --global Dax.Optimizer.CLI --add-source https://api.nuget.org/v3/index.json
```

`--add-source` is not optional in practice: on a machine whose local NuGet
config doesn't already list nuget.org (common on a locked-down corporate
Windows box), the install fails with "not found in NuGet feeds" even though
the package is public. Always pass it.

## Where this runs

| Environment | How the skill invokes it |
|---|---|
| WSL2 driving a Windows host | always through the PowerShell hop: `powershell.exe -NoProfile -Command "daxoptimizer …"` — same pattern as the Desktop bridge |
| Native Windows | `daxoptimizer …` directly, no hop |
| Linux/macOS, no Windows host | the CLI itself is cross-platform (`dotnet tool install`), but there is no Desktop to extract from, so only the `file` source applies (see `vpax-extraction.md`); the browser login must be able to open a browser from that shell |

Paths handed to the CLI on the Windows side are **Windows paths**, not WSL
paths: `L:\home\<you>\repo\<Report>.pbip` when a drive is mapped to the WSL
root, or the ordinary `C:\Users\<you>\…` on native Windows. `--output` writes
the result zip to that same Windows filesystem — copy it back into the repo's
cache directory (`vpax-extraction.md`) rather than reading it in place.

## Auth

```bash
daxoptimizer login --region <australiaeast|eastus|westeurope>
```

Opens a browser at Tabular Tools' own Azure B2C login page. The user signs in
there with their own Tabular Tools account (password or a Microsoft work
account) — **the skill never sees or types a credential**; it only tells the
user "a browser window opened, please complete the sign-in" and waits.
`--group-account <name>` is for group/team licences that share a seat pool.

`--username`/`--password` on `login` and on `analyze` is PAT
(non-interactive) authentication. It is **Enterprise-only** and out of scope
for this skill — we always use the interactive browser flow.

| Command | Purpose |
|---|---|
| `daxoptimizer account show` | cheap "am I logged in" check — prints JSON with `username`, `tenantType`, `personalWorkspaceId` |
| `daxoptimizer logout` | clears the cached credentials |

Token lifetime is undocumented. Treat any auth-shaped failure from `analyze`
or `workspace` as "re-run `login`", not as a bug.

## Discovery

```bash
daxoptimizer workspace list
daxoptimizer workspace model list <workspaceId>
```

`workspace list` returns the workspaces the account can see (a Desktop
licence typically has just the personal workspace). `workspace model list`
returns the models registered in that workspace, each with `modelId`,
`contractId`, and `isSlotEnabled`. `isSlotEnabled: false` means the model
occupies an inactive slot and **cannot be analysed** until it's reactivated —
check this before picking a `--model-id`.

## `analyze`

```bash
daxoptimizer analyze <path-to-vpax> --workspace-id <workspace-id> --model-id <model-id> --output <result>.zip [--wait-timeout <minutes>]
```

| Option | Notes |
|---|---|
| `<path>` (positional) | path to the `.vpax`/`.ovpax`, Windows-side path when run through PowerShell |
| `-w, --workspace-id` (required) | target workspace |
| `-m, --model-id` | target model; omit only when using the experimental name-based flow below |
| `-c, --contract-id`, `--model-name`, `--model-create` | **EXPERIMENTAL**, per the tool's own help text. `--model-create` needs `--model-name` + `--contract-id`. Don't use these — create/register the model in the web app instead and pass `--model-id` |
| `-o, --output` | path to save the result zip; without it you get console output only, no JSON to parse |
| `--fail-on-issues` | non-zero exit if the analysis found issues — a CI knob, not useful for an interactive report run |
| `--wait-timeout` | minutes to wait for the async analysis; default 10, plenty for a model with hundreds of measures |
| `-u/--username`, `-p/--password`, `-r/--region` | PAT auth, Enterprise-only, not used here |

The zip at `--output` contains exactly `DaxOptimizer.json` and
`[Content_Types].xml`; the JSON is the whole result (see `result-json.md`).

## Run economics — read this before calling `analyze`

Every `analyze` call is **one run**, whether or not it finds anything. A
Desktop licence gives **20 runs/day** and **5 active model slots**, Desktop
models only (no Service/XMLA models — see `vpax-extraction.md`). Uploading
and the compatibility check that follows do *not* by themselves cost a run,
but the CLI has **no upload-only command and no "download the previous
result" command** — the only way to get a JSON out of the service is
`analyze`, and that always re-runs the analysis. So:

- **Cache the result zip and re-read it** instead of re-running `analyze` for
  the same model version. Re-analysing an unchanged VPAX just burns a run for
  an identical JSON.
- Before every `analyze` invocation, the skill states plainly: *"this will
  consume 1 of today's 20 runs, on model `<name/id>`"* — and gets explicit
  consent first. There is no dry-run flag.

## What a healthy run looks like

```
Uploading VPAX file …
compatibility: Unknown → (~20s) → Full
Starting analysis …
status: Queued (expectedCompletionOn +5 min)
status: Completed, optimizerResult: Succeeded
Downloading analysis results …
Command succeeded [0]
```

~1 minute end-to-end for an 800-measure model.

`optimizerResult: SucceededWithErrors` is **not a failure** — exit code is
still 0 and the zip still downloads. It means `messages[]` in the JSON lists
specific objects the analyser couldn't parse, e.g. an SVG measure that trips
"Invalid parameter specification: EXPR cannot be used with Scalar". Report
those as "not analysed", don't treat the run as broken.

## Terms and account hygiene

One account per person, no sharing an account or its token cache between
users or machines. KB content at `kb.daxoptimizer.com` is Tabular Tools' IP —
the skill links to articles and writes its own short summary, it never
copies article text into this repo. Proposing and applying fixes is a
separate skill; this one stops at the report.
