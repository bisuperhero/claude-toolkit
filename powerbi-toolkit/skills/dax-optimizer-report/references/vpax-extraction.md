# Getting a VPAX

`daxoptimizer analyze` needs a VPAX file: model metadata (tables, columns,
measures with their DAX, relationships) **plus statistics read from the
data** (row counts, cardinalities). A VPAX exported without statistics is
rejected by the service as "unsupported" — none of the sources below skip
that step by default, don't disable it.

Three sources, in the order this toolkit prefers them:

## 1. `file` — an existing VPAX the user already has

A `.vpax`/`.ovpax` produced by DAX Studio's GUI ("Export Metrics"), Tabular
Editor 3's VertiPaq Analyzer view, or Bravo. Works from any OS, since it's
just a file — hand it straight to `daxoptimizer analyze`. This is the
simplest mode and the only one available on Linux/macOS.

## 2. `desktop` — DAX Studio CLI against a running Power BI Desktop

**Windows-only.** The verified working incantation:

```powershell
& 'C:\Program Files\DAX Studio\dscmd.exe' vpax '<out>.vpax' -s '<Report>.pbip' -d '<GUID>'
```

Two gotchas, both confirmed by trial and error against the help text:

- `-s` must be the **bare file name** (`<Report>.pbip`), not a full path. A
  full path fails with `Unable to find a running Power BI Desktop instance` —
  dscmd matches it against the title of a running Desktop window, not the
  filesystem.
- `-d <GUID>` is **required** even though the help text shows it as an
  option. Without it: `The database '' could not be found`.

Statistics from data are read **by default**; `-r`/`--donotreadstatsfromdata`
turns that off — don't pass it, or the VPAX will be rejected downstream.
Takes a few seconds.

### Finding `<GUID>`

`<GUID>` is the tabular catalog name of the running Desktop instance's
internal Analysis Services database, not anything visible in the Desktop UI.

1. Run `dscmd.exe vpax` once without `-d` — the error/log output includes a
   line like `Found running instance of '<name>' on port: <port>`. That gives
   you the port directly.
2. If you need to find the port independently: map `PBIDesktop.exe` → its
   child `msmdsrv.exe` → the port that process listens on:
   ```powershell
   Get-CimInstance Win32_Process -Filter "Name='msmdsrv.exe'" | Select ProcessId,ParentProcessId
   Get-NetTCPConnection -State Listen
   ```
3. With the port known, query the catalog name over ADOMD using the DLL
   shipped inside the DAX Studio install (no separate ADOMD install needed):
   ```powershell
   powershell.exe -NoProfile -Command "$dll = Get-ChildItem 'C:\Program Files\DAX Studio' -Recurse -Filter 'Microsoft.AnalysisServices.AdomdClient.dll' | Select-Object -First 1 -ExpandProperty FullName; Add-Type -Path $dll; $c = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection('Data Source=localhost:<port>'); $c.Open(); $cmd=$c.CreateCommand(); $cmd.CommandText='SELECT [CATALOG_NAME] FROM $SYSTEM.DBSCHEMA_CATALOGS'; $r=$cmd.ExecuteReader(); while($r.Read()){ $r[0] }; $c.Close()"
   ```
   `Add-Type` prints a `ReflectionTypeLoadException` to the console — that's
   noise from unrelated assemblies in the same folder; the query still runs
   and returns the GUID. Ignore it.

Also useful: `powerbi-desktop status` (the Desktop bridge — see
`desktop-bridge.md` in the `powerbi-report-editing` skill) tells you which
report file each running instance has open and its `hasUnsavedChanges` flag.
**If `hasUnsavedChanges` is true, the VPAX reflects the in-memory model, not
what's in git** — say this explicitly in the report's metadata so nobody
mistakes the analysis for a review of committed DAX.

`te vertipaq --export x.vpax [--obfuscate] --local` is a simpler one-liner
when a Windows build of Tabular Editor's `te.exe` CLI happens to be present —
mention it as an alternative, but it's early-preview and not guaranteed to be
installed; don't make the skill depend on it.

## 3. `xmla` — against a published workspace endpoint

`vpax export` (NuGet `Dax.Vpax.CLI`) or `te vertipaq --export` can target an
XMLA endpoint instead of a local Desktop instance. This needs a
Fabric/Premium workspace with the XMLA endpoint enabled, **and** a
Service/Enterprise DAX Optimizer licence — a Desktop licence cannot analyse
models reached this way at all (Desktop licence = Desktop models only). Out
of scope for a Desktop-licensed setup; only relevant if a client project
later needs a Service licence.

## Obfuscation

For a client model whose names/DAX/cardinalities shouldn't leave the
building in the clear:

```powershell
& 'C:\Program Files\DAX Studio\dscmd.exe' vpax '<out>.ovpax' -s '<Report>.pbip' -d '<GUID>' -i '<out>.dict'
```

The **`.ovpax` extension is what triggers obfuscation** (not a separate
flag); `-i` names the dictionary file to write. To keep names stable across
repeated runs of the same model, reuse the dictionary with
`-n <existing>.dict` (`--InputDictionaryFile`) instead of letting a new one
be generated each time.

Verified facts about obfuscated runs:

- The analysis result is **identical** to the un-obfuscated run — same
  issues, same weights, same rule set. Obfuscation does not degrade the
  analysis.
- **Fingerprints differ** between an obfuscated and un-obfuscated upload of
  the same model version — zero overlap observed. A project must pick one
  mode and stay in it: mixing modes breaks the web app's Fixed/Ignored
  tracking and any local fingerprint-based diff (see `result-json.md`).
- The `.dict` file is plain JSON: `{Id, Version, Texts: [{Value,
  Obfuscated}], UnobfuscatedValues: […]}`. The report script applies it
  locally (`--dict <file>`) to turn obfuscated names back into real ones for
  the human-facing report — see `result-json.md` for how tokens map.
- The dictionary is as confidential as the model itself (it's a reversible
  lookup table) — keep it out of git, next to the VPAX/result cache.

## Where files go

VPAX files and `analyze --output` result zips live in
`.powerbi-cache/dax-optimizer/` inside the project (gitignored), never
committed. The Windows temp folder used during extraction/upload is only a
staging area — copy the final VPAX and result zip into the cache directory
and don't rely on anything surviving in temp.
