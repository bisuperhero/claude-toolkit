# mage-dbt-toolkit

Shared Claude Code setup for Mage.ai (OSS) + dbt + PostgreSQL data pipeline
projects. One install gives every repo the same Mage/dbt knowledge, commit
standard, a reusable CLAUDE.md template, and an `/init-project` command that
drafts a new repo's CLAUDE.md out of what the repo already says — so you stop
re-explaining Mage and stop copy-pasting drifting CLAUDE.md files.

## What's inside

```
mage-dbt-toolkit/
├── .claude-plugin/plugin.json
├── commands/
│   └── init-project.md                 # /init-project — draft a repo's CLAUDE.md, then verify it
├── scripts/
│   └── init-project.py                 # the generator + the --check audit (stdlib only)
├── skills/
│   ├── mage-dbt-conventions/SKILL.md   # shared Mage/dbt mechanics + toolbox DB access
│   ├── mage-new-pipeline/SKILL.md      # scaffold a new extraction pipeline (3-block vs streaming 2-block)
│   └── glitchtip-triage/SKILL.md       # find + fix the top GlitchTip error (interactive)
└── templates/
    ├── CLAUDE.template.md              # copy → <repo>/CLAUDE.md, fill {{PLACEHOLDERS}}
    ├── EXAMPLE-filled-CLAUDE.md        # the template filled in for a fictional project
    ├── COMMIT-STANDARD.md              # Conventional Commits, no emojis
    ├── toolbox-local.yaml.example      # minimal MCP Toolbox config for the dev warehouse
    └── FILL-ME-CHECKLIST.md            # per-project onboarding steps (authoritative)
```

## Install

```
/plugin marketplace add bisuperhero/claude-toolkit
/plugin install mage-dbt-toolkit@bisuperhero-claude-toolkit
```

Machine-wide setup (external tools, MCP servers) is in the marketplace repo's
`INSTALL.md`. Then, for each project, follow `templates/FILL-ME-CHECKLIST.md` —
that is the one authoritative per-project checklist.

## Onboarding a repo

```
/init-project <repo>
```

Drafts `<repo>/CLAUDE.md` from the template with everything the repo can answer
already in place — the Mage and dbt directories, the real dbt layer folders, the
pipeline count, the toolbox `query_<db>` tool names, the warehouse address,
compose profiles and ports, the settings `.env.example` / `io_config.yaml.example`
expect, and the Power BI section or its removal. It never guesses: a value it
cannot read stays a `{{PLACEHOLDER}}` and gets listed at the end, and the command
then interviews you for those. Dry run by default; `--apply` writes, and it
refuses to replace an existing `CLAUDE.md` without `--force`.

```
python3 scripts/init-project.py <repo> --check
```

Audits an existing `CLAUDE.md` for leftover placeholders, empty sections and
unfinished lines — the check nobody used to run. Exit 1 on a finding, so it fits
a pre-commit hook.

## Design principle

- **Skill** = mechanics that are identical everywhere (decorators, pipeline
  pattern, dbt layering, io_config rules, compose). Loaded on demand, costs no
  tokens until relevant.
- **CLAUDE.md** (per repo) = only what differs (sources, prod URL, GlitchTip,
  exact dbt numbering, gotchas). Stays thin.

Update the skill once → every project gets it on next session. No file drift.
