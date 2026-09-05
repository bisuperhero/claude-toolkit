# Thin reports — live connection to a published model

The publish/open/reload steps below need **Power BI Desktop on Windows** (or WSL2
with access to a Windows Desktop install); on Linux or macOS there is no Desktop
to run them against, and only the on-disk file edits apply.

A thin report is `.Report/` only (`.platform`, `definition.pbir`,
`StaticResources/`, `definition/{report.json,version.json,pages/}`) plus a `.pbip`.
There is **no `.SemanticModel/`** — it connects to a semantic model published in the
Power BI Service.

Do **not** copy `.pbi/localSettings.json` when cloning one; it binds the report to
someone else's `reportId` in the Service.

## `byConnection` shape (schema 2.0.0)

`.../item/report/definitionProperties/2.0.0/schema.json` sets
`additionalProperties: false` on `datasetReference.byConnection` and allows exactly
**one** property: `connectionString`. The 1.0-era shape
(`pbiModelDatabaseName`, `connectionType`, `pbiServiceModelId`,
`pbiModelVirtualServerName`, `name`) is rejected with `ObjectNotPerSchema` when
Desktop opens the `.pbip`.

The string Desktop itself writes — workspace by **name**, not GUID:

```
Data Source="powerbi://api.powerbi.com/v1.0/myorg/<Workspace name>";initial catalog="<Dataset name>";access mode=readonly;integrated security=ClaimsToken;semanticmodelid=<dataset GUID>
```

When in doubt, copy a `definition.pbir` from a thin report that is known to open,
and swap the workspace/dataset names and the GUID.

*Verified 2026-09-05 against `definitionProperties/2.0.0` in a report
authored by Power BI Desktop 2.157.1354.0.
A later schema version may accept more properties — re-read the schema itself
before assuming the one-property rule still holds.*

## Editing the model behind a thin report

The report reads the **published** model, not any local TMDL folder — so local
model edits are invisible to it until the model is republished. Worse, an
already-open Desktop instance caches the live connection's schema, so even **after**
publishing it still cannot resolve the new measures. And Power BI **silently drops**
reference labels pointing at unresolvable measures: the card just renders without
them and shows no error at all.

Order of operations when adding a measure a thin report needs:

1. Edit the local TMDL.
2. The user opens the model's `.pbip` and **publishes**.
3. The user **closes and reopens the thin report**. `powerbi-desktop reload` is not
   enough — it reloads the report layer and keeps the stale model schema.

Diagnose "labels are missing but the JSON on disk is correct" as a stale model
schema first, before touching the JSON again.

Because the model is a published dataset, a thin report also cannot solve a
modelling problem by adding a column — e.g. week-offset logic has to be expressed
with the columns the published model already has (see the relative-date section in
`tmdl-and-model.md`).

## You cannot see the model's DAX from here

A thin report has no `.SemanticModel/`, so a measure's definition is simply not
available to the report author — only its name and its description. That is why
measure descriptions in these models carry the DAX after a `---` separator: it is
the only channel through which the formula reaches someone working on the report.
Shape and rules in `tmdl-and-model.md`.
