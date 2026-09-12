# claude-toolkit

A Claude Code **plugin marketplace** with two plugins for data work:

| Plugin | What it gives you |
|---|---|
| **mage-dbt-toolkit** | Conventions for Mage.ai (OSS) + dbt + PostgreSQL pipelines: block structure, dbt layering, new-pipeline scaffolding, GlitchTip error triage, a commit standard, and a reusable `CLAUDE.md` template. |
| **powerbi-toolkit** | Editing Power BI reports and semantic models (PBIR/TMDL) straight from the repo: Tabular Editor CLI, the PBIR authoring CLI, a Desktop bridge, a safe edit protocol, pre-commit checkers for defects the official validator misses, a per-project layout standard, and two DAX Optimizer skills — report (official CLI, user's own login, one licence run per analysis) and fix (approved, verified rewrites). |

`mage-dbt-toolkit` is purely **skill-based**, so it costs no context until Claude
actually needs it. `powerbi-toolkit` is skill-based too, plus six slash commands
for the routine jobs (`preflight`, `doctor`, `describe-measures`,
`measure-catalog`, `dax-optimizer-report`, `dax-optimizer-fix`).

## Supported environments

- The **offline** parts — the Power BI checkers and TMDL/PBIR editing, and all of
  `mage-dbt-toolkit` — run on Linux, macOS, WSL and Windows with Python 3.8+.
- Anything touching a **live** Power BI model — the Desktop bridge, live semantic
  model operations, screenshots — needs Power BI Desktop on Windows, or WSL2 with
  access to a Windows host running it.
- `mage-dbt-toolkit` is OS-agnostic: it talks to Docker and to MCP servers, and
  assumes nothing about the host.

## Requirements

- **Python 3.8+** (for the Power BI checker scripts).
- **powerbi-toolkit**: Tabular Editor CLI (`te`) on PATH, the
  `powerbi-report-author` npm CLI; optionally the `powerbi-desktop` bridge and the
  Power BI Modeling MCP server for live-model work. Check what a machine actually
  has with `/powerbi-toolkit:preflight` (or
  `python3 powerbi-toolkit/skills/powerbi-report-editing/scripts/preflight.py`) —
  it prints each tool's version, what a missing one blocks and how to install it,
  and knows that Power BI Desktop cannot exist on Linux or macOS.
- **mage-dbt-toolkit**: the toolbox MCP server (Google's *MCP Toolbox for
  Databases*) for warehouse access; optionally the GlitchTip MCP server for error
  triage.

Install commands and verification steps for each are in `INSTALL.md`.

## Install

```
/plugin marketplace add bisuperhero/claude-toolkit
/plugin install mage-dbt-toolkit@bisuperhero-claude-toolkit
/plugin install powerbi-toolkit@bisuperhero-claude-toolkit
```

Install only what a repo needs — data work and report work are orthogonal.
Verify with `/plugin`; you should see the skills `mage-dbt-conventions`,
`mage-new-pipeline`, `glitchtip-triage`, `dbt-ship`, `powerbi-report-editing`,
`dax-optimizer-report`, `dax-optimizer-fix` and the commands
`/powerbi-toolkit:preflight`, `/powerbi-toolkit:doctor`,
`/powerbi-toolkit:describe-measures`, `/powerbi-toolkit:measure-catalog`,
`/powerbi-toolkit:dax-optimizer-report`, `/powerbi-toolkit:dax-optimizer-fix`. Commands installed from a plugin are
namespaced with the plugin's name, so it is always the prefixed form you type.

### Updating

Plugins are installed as a **versioned copy**, not read live from the
marketplace. A new commit here does nothing on your machine until you run both:

```
/plugin marketplace update bisuperhero-claude-toolkit
/plugin update powerbi-toolkit@bisuperhero-claude-toolkit    # restart to apply
```

(If you contribute a change, bump `version` in the plugin's
`.claude-plugin/plugin.json` — without that, nobody's update picks it up.)

## How it's meant to be used

- **Skills** carry the mechanics that are identical everywhere. Update once,
  every project gets it next session — no copy-paste drift.
- **Your repo's `CLAUDE.md`** carries only what differs: source systems, prod
  URLs, GlitchTip org/project, dbt layer numbering, the Power BI reports path,
  gotchas. `mage-dbt-toolkit/templates/` has a template, a fill-in checklist,
  and a worked example.
- **Nothing project-specific lives in this repo.** The examples in the skills
  are deliberately anonymous — they show the shape of a real finding, not whose
  data it came from.

Setting up: `INSTALL.md` (once per machine), then
`mage-dbt-toolkit/templates/FILL-ME-CHECKLIST.md` (once per repo).

## Non-goals

- **No deployment to the Power BI Service.** Everything happens against files in
  the repo and, optionally, a local Desktop instance. Publishing stays yours.
- **No editing of legacy `.pbix` as a binary.** The Power BI plugin works on the
  PBIP/PBIR/TMDL text layout; a `.pbix` has to be converted first.
- **No offline DAX validation.** The checkers catch structural defects, not DAX
  semantics — for that you need a real engine.
- **Not a replacement for dbt docs.** The Mage/dbt skill covers conventions and
  mechanics, not your model documentation or lineage.

## Machine-specific paths

The Power BI skill needs external tools (Tabular Editor, the PBIR authoring CLI,
the Desktop bridge) whose paths differ per machine — see `INSTALL.md`, section 2
(*Machine-wide tools*). Keep your own paths in a gitignored `LOCAL.md` or in
`~/.claude/CLAUDE.md`, not in this repo.

## Tested with

Versions this has actually been exercised against. `—` means it has not been
pinned down, not that other versions are known to fail.

**PBIR is not one version.** Every `visual.json` carries the schema version it
was last written with, and Power BI Desktop upgrades a visual only when it
re-saves that visual — so a single report holds a spread of `visualContainer`
versions side by side. Nothing in this toolkit rewrites a `$schema` declaration;
edits are made in place so each file keeps the version Desktop gave it. Treat a
version below as "seen in a real report", not as a requirement.

| Tool | Version |
|---|---|
| Tabular Editor CLI (`te`) | 0.5.2 — **early preview, expires 2026-09-30** |
| `powerbi-report-author` | 0.1.4 |
| Power BI Desktop | 2.157.1354.0 64-bit (August 2026) |
| PBIR schemas | report 3.3.0, page 2.0.0–2.1.0, visualContainer 2.4.0–2.12.0 (mixed within one report — see the note above) |
| Python | 3.12 (min. 3.8) |
| Mage.ai (OSS) | 0.9.79 |
| dbt-core | 1.8.7 |

The Tabular Editor CLI ships as a time-limited **early preview**: the build above
refuses to run after its expiry date, taking DAX formatting and every offline TMDL
operation with it, and nothing in the error names the reason. Download a newer
build from <https://tabulareditor.com/downloads> when that date approaches;
`preflight.py` reads it out of `te`'s own banner and warns inside 30 days.

## License

MIT — see `LICENSE`.
