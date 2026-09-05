# Per-project setup — where to look

Onboarding a repo is described **once**, in the checklist that ships with the
plugin:

> `mage-dbt-toolkit/templates/FILL-ME-CHECKLIST.md`

That is the authoritative copy. After `/plugin install mage-dbt-toolkit@…` it is
on your disk inside the installed plugin, so you can follow it without cloning
this repo. This file only covers the marketplace-level part that has to happen
before it.

## Install the plugins (once per machine)

```
/plugin marketplace add bisuperhero/claude-toolkit
/plugin install mage-dbt-toolkit@bisuperhero-claude-toolkit
/plugin install powerbi-toolkit@bisuperhero-claude-toolkit   # only where there are reports
```

Verify with `/plugin`; you should see the skills `mage-dbt-conventions`,
`mage-new-pipeline`, `glitchtip-triage` and (if installed)
`powerbi-report-editing`.

Full machine setup — external tools and MCP servers — is in `INSTALL.md`.

## Then, per repo

Follow `mage-dbt-toolkit/templates/FILL-ME-CHECKLIST.md`: CLAUDE.md from the
template, MCP servers (toolbox, GlitchTip), Power BI layout file if applicable,
per-project memory, and a short verification pass.
