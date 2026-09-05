# Power BI Desktop bridge — driving a running Desktop

Everything in this file requires **Power BI Desktop on Windows** (or WSL2 with
access to a Windows Desktop install); there is no Desktop on Linux or macOS, so
the bridge is simply unavailable there.

Desktop owns the model in memory while a report is open and **rewrites the files on
save**, silently clobbering external edits. The bridge lets you keep Desktop open
and push disk → Desktop instead.

## Paths per environment

The commands below are written for **WSL2 driving a Windows Desktop**, which is
the most awkward of the three setups. Translate as follows before copying
anything:

| | WSL2 → Windows Desktop | Native Windows | Linux / macOS |
|---|---|---|---|
| Invoking the CLI | `powershell.exe -NoProfile -Command "powerbi-desktop …"` | `powerbi-desktop …` directly in PowerShell — there is no `powershell.exe` hop, and no Linux-node shim to fall into | not available |
| Repo path handed to Desktop | the Windows side of the mapping, e.g. `L:\home\<you>\repo\Report.pbip` when `L:` is mapped to the WSL root — **your mapping will differ** | the ordinary Windows path, `C:\Users\<you>\repo\Report.pbip` | — |
| Windows drives seen from the shell | `/mnt/c/…` | plain `C:\…`; `/mnt/c/…` does not exist | — |
| VS Code extension binaries | `~/.vscode-server/extensions/<ext>-linux-x64/…` | `%USERPROFILE%\.vscode\extensions\<ext>-win32-x64\…` | — |

On Linux or macOS, everything the bridge does — `status`, `reload`, screenshots,
the XMLA mirroring loop — has no equivalent. Offline PBIP/TMDL editing still
works; verification has to happen on a machine that has Desktop.

## From WSL2, always invoke it through PowerShell

```bash
powershell.exe -NoProfile -Command "powerbi-desktop status"
```

The same name is also on the WSL PATH as a `#!/bin/sh` shim
(`/mnt/c/Users/<you>/AppData/Roaming/npm/powerbi-desktop`). **Called directly from
WSL it runs under Linux node, returns `UNSUPPORTED_OS` and an empty `instances`
list** — which looks exactly like a broken bridge or a closed Desktop. Before
concluding the bridge is down, check you went through `powershell.exe`.

## Commands (verified against the installed CLI)

| Command | What it does |
|---|---|
| `status [--pid] [--wait-seconds <s>]` | bridge instances, current file paths, unsaved-change state, PBIR page list |
| `manifest [--pid]` | the bridge manifest for a running PBIDesktop.exe |
| `open <report> [--timeout <s>]` | opens a PBIP/PBIX **in a new Desktop instance** and waits for the bridge |
| `reload [--pid] [--wait-seconds <s>]` | reloads the current PBIP/PBIR from disk |
| `screenshot <page-id> [--pid] --output <path>` | one page to PNG |
| `screenshot-all [--pid] --output <dir>` | every page in `pages.json` |

`status` defaults to `--wait-seconds 0`, so it can answer `not_connected` simply
because the bridge has not finished coming up. Give it a few seconds before
believing that answer, especially right after `open`.

## Opening a report correctly

`open` **always starts a new `PBIDesktop.exe`** — it never attaches to a running
one. That makes it right in one situation and wrong in another:

- **Nothing is open yet → use it.** `powershell.exe -NoProfile -Command
  "powerbi-desktop open 'L:\home\...\Report.pbip' --timeout 120"` launches
  Desktop and waits for the bridge, then `status` gives you the `pid` for the rest
  of the loop. This is the clean way in.
- **The file is already open → never use it.** You would end up with two Desktop
  instances on the same files, which is the one thing the safe edit protocol exists
  to prevent. Use `reload` (report layer) instead.

So the sequence is always: `status` first → decide → `open` only when the target
is genuinely not open.

**To get model (TMDL) changes into Desktop**, the same rule gives the correct
procedure: have the user close the file (verify with `status` → `not_connected`),
then `open` it again — the fresh instance reads the new TMDL. That is not a
workaround for `open`'s behavior, it is the intended use of it.

## The loop

1. `powerbi-desktop status` → `pid`, page list, `hasUnsavedChanges`. It **must** be
   `false` before you edit and reload, otherwise Desktop's unsaved work is lost.
   `not_connected` is also how you confirm a report is closed before editing on
   disk.
2. Edit the files on disk. Under WSL2, Desktop reaches the WSL filesystem through
   a mapped drive, so it is the same bytes — no copy step. Every `L:\…` path here
   is one machine's mapping of the WSL root; substitute your own, or the ordinary
   Windows path when running natively (see **Paths per environment**).
3. `powerbi-desktop reload --pid <pid>` — loads disk → Desktop and discards
   unsaved in-memory edits; disk is the source of truth.
4. `powerbi-desktop screenshot <page-id> --pid <pid> --output 'L:\...png'`, then
   Read the PNG.

One driver at a time: don't hand-edit the same objects in Desktop while driving
from disk.

## `reload` does NOT reload the semantic model

This is the single most misleading thing about the bridge. `reload` re-reads the
**report layer (PBIR) only**. Changes under `*.SemanticModel/definition/**/*.tmdl`
are ignored — Desktop re-attaches the model image it had when the file was opened.
(The AS database GUID changes on every reload, which makes it look like something
was reloaded.)

**Symptom:** a visual referencing a newly added measure reports *"Something's wrong
with one or more fields."* after a reload that reported success.

Check what the live instance actually has:

```bash
powershell.exe -NoProfile -Command "& 'C:\Users\<you>\te.exe' ls --local 'Tables/<Table>/Measures' --non-interactive"
```

Two ways forward:

**A. Close and reopen the file** — the simple, correct default. Do **not** run
`powerbi-desktop open` against a file that is still open: it starts a second
PBIDesktop.exe rather than reusing the running one. Close first (`status` →
`not_connected`), then `open` is the right tool for getting back in (see
**Opening a report correctly**).

**B. Mirror the change into the live instance over XMLA** (when you need to keep
iterating without a reopen). If the Power BI Modeling MCP server is registered,
prefer it — it does this natively and handles the GUID churn for you; see
`modeling-mcp.md`. By hand:

1. Find the port: `powershell.exe Get-Process msmdsrv` →
   `Get-NetTCPConnection -OwningProcess <pid> -State Listen`. Workspace port files
   can be stale — take the port from the live process.
2. Find the DB GUID: `te.exe connect localhost:<port> --non-interactive`. It
   **changes after every reload**, so re-discover it every time; strip `\r` when
   parsing PowerShell output.
3. Apply: `te.exe script -s localhost:<port> -d <guid> -S <script.csx> --save`,
   then `te.exe refresh --type calculate`.
4. Keep the on-disk TMDL identical — edit the files first and validate with
   `te validate -m <Model>.SemanticModel/definition`.

Why step 4 matters: if Desktop's in-memory model never learns the TMDL additions, a
later save from Desktop will clobber them on disk.

Note that `te script --save` against a **file path** destroys the PBIP layout —
see `tmdl-and-model.md`. The `--save` above is against a live server, which is fine.

## Screenshot loop practicalities

- Wait **~25 s** after `reload` before taking the screenshot.
- The screenshot is a **clean page with no editing chrome** — judge by it, not by a
  window capture. Inside a selected visual, slicers render differently
  (hover/selection state) and mislead you about which item is active.
- It captures the **viewport only**. To inspect the lower part of a long page,
  temporarily shuffle visuals' Y positions.
- `screenshot-all` grabs every page from `pages.json` in one go — cheaper than a
  call per page when you're checking a whole report.
- Resolution varies with the window, so **recalibrate page pixels on every
  screenshot** from a known element (e.g. the horizontal extent of a header band of
  known width = page x 0…1920).
- The real bottleneck of any styling task is this cycle, not the model doing the
  work. Batch many changes into one reload+screenshot round.

## When the bridge stops responding after a Desktop update

Symptoms: `BRIDGE_UNAVAILABLE` / `write EOF`; the pipe
`\\.\pipe\pbi-desktop-bridge-<pid>` is created but Desktop closes the connection
immediately at zero bytes.

Known cause (Desktop 2.157.879.0, 2026-08 —
[skills-for-fabric#76](https://github.com/microsoft/skills-for-fabric/issues/76)):
the upgrade deleted `PolyType.dll` and `Nerdbank.MessagePack.dll` from
`C:\Program Files\Microsoft Power BI Desktop\bin\`. `StreamJsonRpc 2.25` depends on
them, so `JsonRpc.Attach()` died with `FileNotFoundException`.

Fix: MSI repair, elevated —
`msiexec /fp "{9c8b43e8-19cc-474e-a871-a6926562923f}"`.

So when the bridge goes quiet right after a Desktop update, check those two DLLs
first instead of assuming the bridge is unusable and falling back to a restart loop.
