# The measure catalog — a help page that cannot go stale

The script itself runs anywhere, but the verification steps below — refresh the
model, look at the table in the data view — need **Power BI Desktop on Windows**
(or WSL2 with access to a Windows Desktop install), so the catalog cannot be
signed off from Linux or macOS alone.

Models following this convention park their report-wide measures in one holder
table: `.Measures` in some models, `00 MEASURES` in others. It is always
the same shape — a **calculated table** whose expression is the constant `{1}`,
with one hidden `Value` column that exists only to make the table legal. It holds
measures and documents nothing.

`scripts/measure-catalog.py` rewrites that expression so the table derives itself
from **`INFO.VIEW.MEASURES()`**: one row per visible measure, with the table it
lives in, its display folder, and the two halves of its `///` description — the
prose, and the DAX after the `---` separator. A report binds a table visual to
those columns and gets a help page.

## Why this and not a generated table

The obvious build is a script that reads the TMDL descriptions and writes them
back as a `DATATABLE` of literal rows. Don't. A production model of **1524
measures** makes the cost obvious: that is ~1500 lines of generated TMDL that
churns on every measure edit, goes stale the moment someone renames something in
Desktop, and needs a commit hook to stay honest — a hook that would rewrite
Desktop-owned files behind the user's back.

`INFO.VIEW.MEASURES()` is the engine reading its own metadata at refresh time.
There is nothing to generate, nothing to commit, nothing to keep in sync, and
**no hook to write** — which is the answer to "should this be pre-commit
automation": no, because with this shape there is nothing for a hook to do. What
remains is `doctor.py`, which reports which models still have no catalog.

Microsoft names this exact pattern as the sanctioned use of calculated tables in
Direct Lake — *"A common example is using INFO.VIEW DAX functions to
self-document the semantic model"* ([Editing Direct Lake semantic models in
Desktop](https://learn.microsoft.com/en-us/fabric/fundamentals/direct-lake-power-bi-desktop),
2025-08).

## What the script writes

```dax
SELECTCOLUMNS (
    ADDCOLUMNS (
        FILTER ( INFO.VIEW.MEASURES ( ), NOT [IsHidden] ),
        "@Separator", SEARCH ( "---", [Description], 1, 0 )
    ),
    "Table",       [Table],
    "Measure",     [Name],
    "Folder",      [DisplayFolder],
    "Description", TRIM ( IF ( [@Separator] = 0, [Description], LEFT ( [Description], [@Separator] - 1 ) ) ),
    "DAX",         TRIM ( IF ( [@Separator] = 0, BLANK ( ), MID ( [Description], [@Separator] + 3, LEN ( [Description] ) ) ) )
)
```

Column names follow the project's language (section 6 of its layout file).
`--lang en` (the default) writes the English names shown above; `--lang cs`
writes the Czech equivalents (`Tabulka | Míra | Složka | Popis`).

**The formula column deliberately does not use `INFO.VIEW.MEASURES()[Expression]`.**
That column — along with `[DetailRowsDefinition]` and `[FormatStringDefinition]` —
is permission-gated: it returns blank for anyone without **write** permission on
the semantic model, which is every report consumer, and blank in Desktop over a
live connection. `[Description]` carries no such gate. So the `---` DAX block that
`tmdl-and-model.md` already requires in every description is what makes the
formula reachable on a help page at all. Two conventions, one payoff.

## Running it

```bash
python3 <skill-dir>/scripts/measure-catalog.py <repo>                    # dry run
python3 <skill-dir>/scripts/measure-catalog.py <repo> --apply
python3 <skill-dir>/scripts/measure-catalog.py <repo> --check            # what doctor runs
python3 <skill-dir>/scripts/measure-catalog.py <repo> --create '01 MEASURE CATALOG' --apply
```

Dry-run by default, honors `.powerbi-scan-ignore`, re-running is a no-op — column
`lineageTag`s are kept, so report bindings survive a second run.

It finds the holder by **shape, not by name** (a calculated table with a constant
expression that carries measures), because the name differs per project. Two
things stop it:

- **The holder's own columns are bound by a visual.** Real case: a model whose
  holder has a hidden `Missing column` that slicers across two reports bind to. A
  calculated table can only expose the columns its expression produces, so the
  rewrite would break them — the script refuses and names the files. Use
  `--create '<name>'` there: the catalog goes into its own table and the holder is
  left alone.
- **The partition is not `calculated`.** A loaded table is never touched.

`--create` is also how models with no holder table at all
get one — it writes the table file and registers `ref table` in `model.tmdl`,
which is what makes TMDL load it. In a repo where some models were already
converted in place it skips those, so one `--create` pass over a mixed repo does
not give anybody a second catalog.

## First run — verify on one model, then roll out

Two things in this design are **not** verified by anything on disk, and `te
validate` will not catch either (it loads metadata, it does not evaluate DAX):

1. **Circular dependency.** The catalog table also hosts measures, so it reads
   metadata that includes its own measures. No report of this failing exists, and
   Microsoft's own examples do it — but nobody has written down a test. Open one
   model in Desktop, refresh, and confirm the table populates.
2. **Newlines through the description.** Whether the line breaks in a `///` block
   survive into `[Description]` and back out. Look at the `Description` column in
   the Desktop data view before designing the page around it.

So: Desktop **closed**, run `--apply` on one model, open it, refresh, look at the
table. Only then run the rest. Commit the model change on its own.

After publishing, the Service needs **one more refresh** before the catalog shows
new measures — publishing alone does not recalculate it. This is the failure mode
a help page hits in production: someone adds a measure, republishes, and the help
page still shows the old list.

## Building the help page

- **Table visual**, columns in the order `Table | Measure | Description` (+ `DAX`
  if the audience is analysts). Turn **Values → Text wrap on**, or every multi-line
  description silently collapses to a single line — Power BI ignores newline
  characters in table cells by default
  ([Learn](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-tables)).
- Power BI sizes a table from **the first 20 columns and first 50 rows**, so with
  long descriptions further down the column widths come out wrong. Set them.
- A **text slicer on `Measure`** plus a slicer on `Table` is what makes the page
  usable at 1500 rows.
- The new **card visual's Detail slot ignores `UNICHAR(10)`** even with wrap on —
  don't build the detail pane out of cards.
- `[DataType]` is reported to come back blank inside a calculated table. Don't add
  a column on it without checking first.

The last two are Power BI Desktop rendering/engine behaviors rather than facts
about the model, and no verification date or Desktop build was recorded for
either — re-check both against the Desktop build you are on before designing a
page around them.

## What it does not do

- **Hidden measures are excluded by `NOT [IsHidden]`, and that is the only filter.**
  Perspectives are ignored entirely, and object-level security does not redact
  rows that were materialized at refresh. If a measure's *name* is confidential,
  a catalog in that model is the wrong place for it.
- **Technical measures still show up** — color constants, `_empty`, `Missing` —
  unless they are hidden. Hide them in the model, or add a
  `NOT ( LEFT ( [DisplayFolder], 1 ) = "." )` clause to the `FILTER` if the
  project parks them in dot-prefixed folders.
- **A thin report cannot create this.** Modeling is disabled under a live
  connection; the catalog has to exist in the published model, and the thin report
  binds to it like any other table.
- **It does not write descriptions.** Garbage in, garbage on the help page — the
  catalog is only as good as `check-measure-descriptions.py` says coverage is.
