# Global preferences snippet (optional example)

**This file is optional and prescribes nothing.** It is the author's own global
preferences, shown as one example of the kind of thing that belongs in
`~/.claude/CLAUDE.md` rather than in a project — machine-wide working style, not
project facts. Your preferences will differ; treat this as a shape to copy, not a
list to adopt. Nothing in the plugins depends on it.

They were extracted from recurring feedback across projects. Paste what you like
into your global `~/.claude/CLAUDE.md` — not into a per-repo CLAUDE.md.

---

## Working style

- Read-only operations (read / grep / find / ls, and `git` read commands) proceed
  without asking. Ask for confirmation only before changes (edits, writes, commits,
  deploys, anything against production).
- dbt in a venv: chain `source .venv/bin/activate && dbt ...` without a separate
  confirmation step.

## File locations

- Screenshots / printscreens live under `<your screenshots dir>/YYYY-MM/` by
  current month. Look there when asked about a screenshot. (Substitute your own
  path — e.g. the download folder your screenshot tool writes to.)

---

Optional: instead of pasting, the read-only/venv items are better expressed as
`permissions.allow` entries in `~/.claude/settings.json` (e.g. `Bash(grep *)`,
`Bash(find *)`, `Bash(source .venv/bin/activate && dbt *)`), so they don't consume
context on every turn. Per-project `settings.local.json` files tend to accumulate
the same allow-rules over time — worth consolidating the safe ones into the
global settings.
