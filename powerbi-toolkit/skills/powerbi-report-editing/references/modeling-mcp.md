# Power BI Modeling MCP server — live semantic-model work

Attaching to a model open in **Power BI Desktop** requires Desktop on Windows (or
WSL2 with access to a Windows Desktop install); on Linux or macOS only the Fabric
service target is reachable.

**Maturity of this reference:** the server registers and loads in Claude Code (the
`mcp__powerbi-modeling__*` tools appear once the session picks it up) and its tool
list below is confirmed. An end-to-end edit against a running Desktop instance has
not been exercised through this toolkit, so treat the connection step as unverified
and check it on first real use.

An **optional** but much better path for editing a model that is **live** (open in
Desktop, or hosted in the Fabric service) than scripting `te.exe` over XMLA.

Ships inside the VS Code extension
[`analysis-services.powerbi-modeling-mcp`](https://marketplace.visualstudio.com/items?itemName=analysis-services.powerbi-modeling-mcp)
as a **standalone stdio MCP server**, so it is not tied to VS Code:

```
<vscode-extensions>/analysis-services.powerbi-modeling-mcp-<version>-linux-x64/server/powerbi-modeling-mcp
```

## Registering it with Claude Code

```bash
claude mcp add powerbi-modeling -- \
  ~/.vscode-server/extensions/analysis-services.powerbi-modeling-mcp-<version>-linux-x64/server/powerbi-modeling-mcp \
  --readonly
```

Flags: `--start` (ReadWrite, the extension's default), `--readonly` / `--read-write`,
`--require-confirmation` (confirmation prompts on writes — off by default),
`--authmode=serviceprincipal|interactive|managedidentity|azurecli`,
`--compatibility=powerbi` (default) or `full` (adds Analysis Services).

**Start read-only.** The default mode is read-write with confirmations *skipped*,
against a live model. Register `--readonly` for inspection work and switch
deliberately when a task needs writes.

The version is part of the path, so an extension upgrade moves the binary —
re-point the registration when it stops launching.

The path above is the WSL2 / Linux one. On native Windows the extension lives
under `%USERPROFILE%\.vscode\extensions\analysis-services.powerbi-modeling-mcp-<version>-win32-x64\server\powerbi-modeling-mcp.exe`
— see "Paths per environment" in `desktop-bridge.md`.

## What it exposes

21 tool families over the live model. The ones that matter here:

| Tool | Use |
|---|---|
| `connection_operations`, `database_operations` | attach to a model in **Power BI Desktop** or the Fabric service |
| `measure_operations`, `column_operations`, `table_operations` | CRUD, single or batched |
| `dax_query_operations` | **Execute, Validate**, ClearCache |
| `relationship_operations`, `user_hierarchy_operations`, `calculation_group_operations` | model structure |
| `partition_operations`, `model_operations` | refresh, including `RefreshWithXMLA` |
| `transaction_operations` | Begin / Commit / Rollback |
| `security_role_operations`, `perspective_operations`, `culture_operations`, `object_translation_operations` | roles, perspectives, translations |
| `trace_operations` | capture Analysis Services events |

`dax_query_operations` **Validate** is worth knowing about on its own: it is the
only tool in this toolkit that checks DAX before you commit it.

## When to use it, and the catch

Use it for **live** model work — the case `desktop-bridge.md` otherwise solves by
hand (find the `msmdsrv` port → re-discover the database GUID → `te.exe script
--save` → `refresh --type calculate`). The MCP does that natively and survives the
GUID churn.

Keep using `te` and direct TMDL edits for **offline** work on the PBIP folder;
that is what the files-on-disk protocol is built around.

**The catch is the same as with any live edit:** this changes the model *in memory*,
not the TMDL on disk. Desktop still rewrites the files on save, so a live-only
change either gets clobbered or silently diverges from git. Mirror every change
into `*.SemanticModel/definition/**` and validate with
`te validate -m <Model>.SemanticModel/definition`, exactly as in
`desktop-bridge.md`.
