# Editing inside a `.pbix`

Unpacking and repacking is plain zip work and runs anywhere; confirming that the
repacked file actually opens needs **Power BI Desktop on Windows** (or WSL2 with
access to a Windows Desktop install), so never hand over a repacked `.pbix` that
has not been opened on such a machine.

`.pbix` is an OPC zip, not an opaque binary. Look inside before deciding anything:

```bash
unzip -Z1 file.pbix
```

- `Report/definition/…` present → **PBIR, the report is editable.** This has been
  the Desktop default since roughly the start of 2026; in a surveyed production
  repo 16 of 23 `.pbix` files are like this. *Observed on Power BI Desktop builds
  up to 2.157.879.0; no verification date recorded — re-check the default on a
  newer build before relying on it.*
- `Report/Layout` (a single UTF-16 JSON blob) → legacy format, **don't edit**.
- `DataModel` → always binary, **never touch**.

Thin vs. thick is not the criterion for editability, and the presence of a model
does not forbid editing the report — it only bounds what you may touch. Classify by
the zip's contents, never by the file extension.

Editing an unpacked `*.Report/` beside a `.pbip` is less fragile than round-tripping
a `.pbix`; prefer it when both exist.

## Repacking: drop `SecurityBindings`

When you unpack a `.pbix`, change JSON, and pack it back, you **must** remove the
`SecurityBindings` part **and** its line in `[Content_Types].xml`:

```xml
<Override PartName="/SecurityBindings" .../>
```

Otherwise Desktop refuses the **whole file**:

> This file is corrupted or was created by an unrecognized version of
> Power BI Desktop. It can't be opened.

(In the feedback blob: `PowerBINonFatalError_ErrorCode: MashupValidationError`,
`Model Default Mode: Empty`, stack through `TryOpenOrCreateReport`.)

`SecurityBindings` is a DPAPI blob (it starts with provider
`d08c9ddf-0115-d111-8c7a-00c04fc297eb`) that binds the package contents. Repacking
changes report parts while the signature stays byte-for-byte identical, so it stops
matching. Dropping it makes the file behave as unsigned, which opens fine — this is
what `pbi-tools` does too.

**Build it into the script**, don't remember to do it — it has been missed on at
least two separate files in practice:

```python
for info in src.infolist():
    if info.filename == "SecurityBindings":
        continue
    ...
```

plus a regex that strips the `Override`. Preserve everything else — entry order,
`compress_type`, `date_time`.

**Verify before handing over:** `SecurityBindings` is absent from `namelist()` and
from `[Content_Types].xml`, and `testzip()` returns `None`.

## Two false leads that cost time

- `powerbi-report-author validate` **cannot see** this defect — it is below the
  level of the report definition.
- `daxQueries.json` is legitimately **UTF-16**, so `json.loads` failing on it means
  nothing is wrong.
