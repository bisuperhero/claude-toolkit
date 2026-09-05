# Per-project checklist

Run once per Mage.ai + dbt repo, after the one-time machine setup (`INSTALL.md`
in the marketplace repo). Goal: each repo carries only its own facts; everything
shared comes from the plugins.

This is the authoritative checklist — it ships with the plugin, so it is the copy
you have on disk after installing.

## 1. Plugins

The shared skills and standards live in the `claude-toolkit` marketplace so they
don't get copy-pasted into every repo. You already have `mage-dbt-toolkit` if you
are reading this file from the installed plugin; add the Power BI one only where
there are reports:

```
/plugin install powerbi-toolkit@bisuperhero-claude-toolkit
```

- [ ] Verify with `/plugin` — `mage-dbt-conventions` should be among the
      available skills.

## 2. CLAUDE.md

Run `/init-project <repo>` in the repo. It drafts `CLAUDE.md` from the template
with everything the repo can answer already filled in — project name, the Mage
and dbt directories, the **real** dbt layer folders, the pipeline count, the
toolbox `query_<db>` tool names, the warehouse address, compose profiles and
ports, the settings `.env.example`/`io_config.yaml.example` expect, and the Power
BI section (or its removal). Then it walks you through what no repo can answer,
and verifies the result. That is the whole of this section; the manual route
below is the fallback for when the plugin is not installed.

<details>
<summary>Manual fallback</summary>

- [ ] Copy `templates/CLAUDE.template.md` → `<repo>/CLAUDE.md`. (See
      `templates/EXAMPLE-filled-CLAUDE.md` for how much detail a filled-in one
      carries.)
- [ ] Replace every placeholder:
  - [ ] `{{PROJECT_NAME}}`, `{{MAGE_DIR}}` and `{{DBT_DIR}}`.
  - [ ] **About** — one paragraph of business context (or delete if internal).
  - [ ] **Domain knowledge** — source systems, identifiers, validity and
        soft-delete rules.
  - [ ] **Architecture** — number of extraction pipelines, any secondary dbt
        project.
  - [ ] **dbt layers table** — the actual folder numbering for THIS repo
        (projects legitimately differ — 0–2 and 0–4 both happen, plus variants
        like `2_marts_v2/`). Delete unused rows.
  - [ ] **Infrastructure** — PostgreSQL host, non-standard ports, extra services.
  - [ ] **Connections** — DB host/port/name, source DB access method.
  - [ ] **toolbox tools** — the dev `query_<db>` and prod `query_<db>_production`
        names plus any caveat (e.g. "dev is a truncated sample").
  - [ ] **Production** — prod Mage URL; GlitchTip **organization + project**; the
        prod vs dev environment tag; Slack/Teams channels.
  - [ ] **Power BI** (if applicable) — where the reports live; otherwise delete
        the section.
  - [ ] **Gotchas** — start small, grow as you hit them.

</details>

- [ ] If migrating an existing repo, delete from its old CLAUDE.md anything now
      covered by the skill (block decorators, config → loader → exporter prose,
      generic dbt layering, the io_config "not in repo" note, compose commands).
      Keep only project-specific facts.
- [ ] **Verify it — this is the step that used to get skipped.** Nothing else
      checks that a placeholder survived the copy-paste. Run
      `python3 <plugin>/scripts/init-project.py <repo> --check`: exit 0 = no
      `{{PLACEHOLDER}}` left, no empty sections, no unfinished lines. Exit 1
      lists what is still open — either fill it in or delete the row it lives
      in. Re-run it whenever CLAUDE.md is edited by hand.

## 3. MCP servers (so skills don't fail mid-task)

- [ ] **toolbox** — make sure `toolbox-local.yaml` (and `toolbox-production.yaml`
      if used) exist in the repo root and the toolbox MCP is connected. The skills
      preflight-check for a `query_<db>` tool; without it, DB queries can't run.
      Start from `templates/toolbox-local.yaml.example`.
- [ ] **GlitchTip** (if you triage errors) — connect the project's GlitchTip MCP
      (`https://<glitchtip>/mcp`, server-side `GLITCHTIP_ENABLE_MCP=True`).
- [ ] **Power BI** (if applicable) — the report-editing tools are machine-wide
      (see `INSTALL.md`); no per-repo MCP is needed. For **live** model operations
      the optional `powerbi-modeling` MCP server is registered once, globally.

## 4. Power BI reports (only if the repo has them)

- [ ] Point CLAUDE.md at where the reports live — in this repo (PBIP layout) or in
      a dedicated reports repo.
- [ ] On the first edit, the `powerbi-report-editing` skill generates
      `POWERBI-LAYOUT.md` from the default template, marked UNREVIEWED. **Review
      and adjust it** — page size, gaps, slicer sizes and modes, fonts, colors and
      naming all legitimately differ per project. The skill itself holds no
      formatting values, so this file is the only place they live; record
      deliberate deviations in its section 10.

## 5. Commit messages

- [ ] No per-repo commit file is needed — the standard lives in
      `templates/COMMIT-STANDARD.md` in this plugin. Point the repo's CLAUDE.md at
      it and leave it there.

## 6. Per-project memory (optional but recommended)

- [ ] If migrating from a backup, copy the repo's accumulated
      `.claude/projects/.../memory/` into the real repo — that is tribal knowledge
      the plugins don't (and shouldn't) carry.

## 7. Verify

- [ ] `init-project.py <repo> --check` comes back clean (section 2).
- [ ] Open Claude in the repo and ask a Mage/dbt question — the skill should
      answer without you re-explaining the stack.
- [ ] Ask a project-specific question — the repo's CLAUDE.md should answer it.
- [ ] Run one database query — confirms the toolbox preflight passes.
