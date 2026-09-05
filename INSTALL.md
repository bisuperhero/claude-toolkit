# INSTALL — one-time machine setup

Do this once per machine (a fresh laptop, a new WSL install). Onboarding
individual projects is in `mage-dbt-toolkit/templates/FILL-ME-CHECKLIST.md`
(`PER-PROJECT-CHECKLIST.md` is a short signpost to it).

## 1. Add the marketplace and install the plugins

```
/plugin marketplace add bisuperhero/claude-toolkit
/plugin install mage-dbt-toolkit@bisuperhero-claude-toolkit
/plugin install powerbi-toolkit@bisuperhero-claude-toolkit   # only if you edit PBI reports
```

Working on the toolkit itself? Clone it somewhere stable (e.g.
`~/claude-toolkit`) and add that path instead — same commands otherwise:

```
/plugin marketplace add ~/claude-toolkit
```

Verify with `/plugin` — you should see the skills available:
`mage-dbt-conventions`, `mage-new-pipeline`, `glitchtip-triage`,
`powerbi-report-editing`, and the commands `/powerbi-toolkit:preflight`,
`/powerbi-toolkit:doctor`, `/powerbi-toolkit:describe-measures`,
`/powerbi-toolkit:measure-catalog`.

Pull in later changes with:

```
/plugin marketplace update bisuperhero-claude-toolkit
```

## 2. Machine-wide tools (only if you edit Power BI)

The `powerbi-report-editing` skill *uses* these; it does not install them. Each
one below has an install command and a one-line check that it worked.

**Tabular Editor CLI (`te`)** — offline TMDL edits. A single self-contained
binary; grab the Linux build from <https://tabulareditor.com/downloads>, put it on
PATH and make it executable:

```bash
mkdir -p ~/.local/bin
# download the Linux CLI build, then:
install -m 755 ~/Downloads/te ~/.local/bin/te
```

Check: `te --version` prints a version instead of "command not found".

**It expires.** The current build is an *early preview* that stops running on a
fixed date — `te --help` prints it, e.g. `Early preview expires ... on
2026-09-30`. Past that date DAX formatting and offline TMDL operations fail, with
nothing in the message naming the cause. Re-download from the same page when the
warning gets close; `preflight.py` (below) checks the date for you.

**Tabular Editor CLI, Windows build** — the `--local` flag (live operations
against a running Power BI Desktop instance) is Windows-only. Put the Windows
build at e.g. `C:\Users\<you>\te.exe` and call it from WSL through `/mnt/c/...`.

Check: `/mnt/c/Users/<you>/te.exe --version` from WSL.

**`powerbi-report-author`** — PBIR authoring/preview CLI, installed on the Linux
(WSL) Node:

```bash
npm install -g powerbi-report-author
```

Check: `powerbi-report-author --help` prints usage.

**`powerbi-desktop` bridge** *(optional)* — drives Power BI Desktop; must be
installed on the **Windows** Node, then called from WSL via `powershell.exe`:

```bash
powershell.exe -Command "npm install -g powerbi-desktop"
```

Check: `powershell.exe -Command "powerbi-desktop --help"` prints usage. Power BI
Desktop itself must be installed on Windows for this to do anything.

**Power BI Modeling MCP** *(optional)* — live semantic-model operations. It ships
inside the `analysis-services.powerbi-modeling-mcp` VS Code extension as a
standalone stdio binary, so it can be registered with Claude Code directly:

```bash
claude mcp add powerbi-modeling -- \
  ~/.vscode-server/extensions/analysis-services.powerbi-modeling-mcp-<version>-linux-x64/server/powerbi-modeling-mcp \
  --readonly
```

Register it read-only; the default mode writes to a live model without
confirmation. Details in the skill's `references/modeling-mcp.md`.

Check: `claude mcp list` shows `powerbi-modeling` as connected.

### Check them all at once

```bash
python3 <plugin>/skills/powerbi-report-editing/scripts/preflight.py
```

One table: every tool above, found (with its version) or missing, then what each
missing one blocks and how to install it. It exits 0 when everything usable on
this machine is present, 1 when something is missing or the Tabular Editor preview
has expired, 2 when there is no usable Python at all. On Linux and macOS it
reports the Desktop bridge and live-model work as *not available on this platform*
rather than as something to install — Power BI Desktop is Windows-only — and says
what still works there (offline TMDL/PBIR editing, all seven checks, the bulk
tools). Inside Claude it is `/powerbi-toolkit:preflight`, or `doctor.py --tools`.

## 3. MCP servers (for the Mage/dbt plugin)

**toolbox — database access.** This is Google's
[MCP Toolbox for Databases](https://github.com/googleapis/genai-toolbox): a single
binary that reads a YAML file describing your database sources and exposes each
one as an MCP tool. The Mage/dbt skills preflight-check for a `query_<db>` tool
and refuse to fall back to raw psql, so this is what makes DB work possible.

Install the binary (see the releases page for your platform), then register it
per repo — the config file lives in the repo root:

```bash
claude mcp add -s project toolbox -- \
  /path/to/toolbox --tools-file ./toolbox-local.yaml --stdio
```

Start from `mage-dbt-toolkit/templates/toolbox-local.yaml.example`; copy it to
`<repo>/toolbox-local.yaml` and adjust the source and tool names. Credentials come
from environment variables, never from the committed YAML. (Flag names have
changed between toolbox versions — check `toolbox --help` if registration fails.)

Check: `claude mcp list` shows `toolbox` connected, and the tool list contains
`query_<db>`.

**GlitchTip — error triage** *(optional, only if you use `glitchtip-triage`)*.
Your GlitchTip instance must have `GLITCHTIP_ENABLE_MCP=True` set server-side;
then register its HTTP endpoint:

```bash
claude mcp add --transport http glitchtip https://<glitchtip-host>/mcp
```

If your instance requires authentication, pass a GlitchTip auth token instead of
relying on a browser session:

```bash
claude mcp add --transport http glitchtip https://<glitchtip-host>/mcp \
  --header "Authorization: Bearer <GLITCHTIP_TOKEN>"
```

Keep the token out of the repo — use a shell variable or your OS keychain.

Check: `claude mcp list` shows `glitchtip` connected and the tools include
`list_projects` and `list_issues`.

## 4. Global preferences (optional)

`GLOBAL-CLAUDE-snippet.md` is the **author's** machine-wide preferences, included
as one example of what belongs in `~/.claude/CLAUDE.md` rather than in a project.
Nothing in the plugins depends on it. If you want something like it:

- Paste the working-style and file-location items into your global
  `~/.claude/CLAUDE.md`.
- Better for the read-only/venv rules: add them as `permissions.allow` entries in
  `~/.claude/settings.json` instead, so they don't consume context every turn.
  (Per-project `settings.local.json` files tend to accumulate the same safe
  allow-rules over time — worth consolidating them once.)

## 5. Sanity check

Open Claude in any Mage/dbt repo and ask "what are the dbt layers here and where
does io_config live?" — it should answer from that repo's CLAUDE.md plus the
skill, without you re-explaining Mage.

---

Done. Now onboard each project →
`mage-dbt-toolkit/templates/FILL-ME-CHECKLIST.md`.
