---
description: Check the external Power BI tools are installed before a task needs them, and report what each missing one costs
allowed-tools: Bash(python3:*), Bash(te:*), Bash(powerbi-report-author:*), Bash(powershell.exe:*), Read
---

Find out what is actually installed on this machine **before** starting work that
needs it. The skill drives four tools it does not install — the Tabular Editor
CLI, the PBIR authoring CLI, the Power BI Desktop bridge and the optional
Modeling MCP — and a missing one used to surface as `command not found` halfway
through an edit, long after the point where the task could have been planned
around it.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/powerbi-report-editing/scripts/preflight.py
```

Then:

1. **Read the exit code as a plan, not a verdict.** 0 — everything usable on this
   platform is present. 1 — something is missing or expired; the report already
   says what it blocks and what still works, so the answer to the user is "these
   parts can go ahead, this one cannot", never a bare "no". 2 — no usable Python,
   so nothing in the toolkit runs at all.
2. **Respect the platform line.** On Linux and macOS there is no Power BI Desktop,
   so the bridge, screenshots, the safe edit protocol's `status`/`reload` and
   live-model edits are out of reach by construction — report them as "not
   available on this platform", not as something to install. Offline TMDL and PBIR
   editing, all seven `doctor.py` checks and the bulk tools are unaffected there,
   and saying so is the useful half of the answer.
3. **Take the Tabular Editor expiry seriously.** The tested `te` is an early
   preview build that stops running on a fixed date. Once past it, `te format` and
   offline TMDL operations fail with nothing pointing at the cause. Inside 30 days
   preflight says so — tell the user to download a newer build from
   <https://tabulareditor.com/downloads> rather than waiting for it to break
   mid-task.
4. **Install nothing on the user's behalf.** Report the install command from the
   output and let them run it; these are machine-wide tools, and `INSTALL.md`
   section 2 is the fuller version of the same instructions.
5. **Do not stop for a tool the task never touches.** Editing files and running the
   checkers needs Python and nothing else. A missing bridge does not block an
   offline TMDL edit.

`doctor.py --tools` runs exactly this, for when the repo checks and the tool check
belong in one command. The two are separate modes on purpose: none of the seven
structural checks shells out to an external tool, so a failing check is never a
missing `te`.

If `${CLAUDE_PLUGIN_ROOT}` is not set, the same files sit in the checkout under
`powerbi-toolkit/skills/powerbi-report-editing/`.
