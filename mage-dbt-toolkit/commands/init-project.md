---
description: Draft a Mage/dbt repo's CLAUDE.md from the template, fill in what only you know, and verify nothing is left blank
argument-hint: "[repo path]"
allowed-tools: Bash(python3:*), Read, Write, Edit, AskUserQuestion
---

Onboard a Mage.ai + dbt repo. The script reads out of the repo everything a repo
can tell you; the interview covers the rest. `templates/FILL-ME-CHECKLIST.md` is
the surrounding checklist — this command is step 2 of it.

`$ARGUMENTS` is the repo to onboard; with no argument, use `.`.

## 1. See what the repo already answers

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/init-project.py $ARGUMENTS
```

This is a dry run — it writes nothing. Read the three blocks it prints: what it
read out of the repo, what it could not read, and what would be left as a
placeholder.

**Exit 2 is not a clean run.** It means the path is wrong, the template is
missing, or a `CLAUDE.md` is already there. If one is already there, do **not**
reach for `--force` on your own — run step 4 against it instead and offer to
repair that file, since it may hold hand-written project knowledge the template
cannot regenerate.

Sanity-check the detected values against the repo before writing. A wrong Mage
directory or a dbt project picked from two candidates is worth one `ls`.

## 2. Write the draft

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/init-project.py $ARGUMENTS --apply
```

## 3. Interview the user for the rest

Work through the placeholders the run listed. They are the values no repo
carries, so **never invent one** — an unanswered placeholder left in place is a
correct outcome; a plausible-looking guess is not.

Ask with `AskUserQuestion` where the answer is a choice out of a few, and in
plain prose where it is not:

- **Production** — prod Mage URL, GlitchTip organization and project, the prod
  vs dev `server_name`/environment tag, notification channels. Ask together;
  they come from one place in the user's head.
- **Domain knowledge** — the source systems, their grain and identifiers, the
  validity rules, the soft-delete flag. Copy the source bullet once per system.
- **dbt layer purposes** — one line per `{{PURPOSE_*}}` row. The folder names in
  the table are already the repo's real ones; only the purpose is missing.
- **Business context** — one paragraph, or delete the section for an internal
  project rather than leaving it thin.
- **Toolbox caveats and gotchas** — start the gotchas list empty if the user has
  none; it grows on its own.

Apply the answers with `Edit`, and delete the `<!-- guidance -->` comments in
each section as you fill it in.

## 4. Verify

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/init-project.py $ARGUMENTS --check
```

Exit 0 means no placeholders, no empty sections, no unfinished lines. Exit 1
lists what is still open — report it, and say which entries are open because the
user chose not to answer rather than because they were forgotten. Do not close
out the command on an unexamined exit 1.

Then finish the rest of `templates/FILL-ME-CHECKLIST.md` — the toolbox and
GlitchTip MCP servers, Power BI layout review, per-project memory.

If `${CLAUDE_PLUGIN_ROOT}` is not set, the same files sit in the checkout under
`mage-dbt-toolkit/`.
