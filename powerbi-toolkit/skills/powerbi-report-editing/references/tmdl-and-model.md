# TMDL, M and DAX — editing the semantic model

## `te … --save` destroys the PBIP folder layout

This is **not specific to `script`** — it is how `te` re-serializes a model when
asked to save it back to a file path. Verified on a copy for both subcommands:

| Command | Result |
|---|---|
| `te script <model> -S x.csx --save` | flattens the model, deletes `definition/` |
| `te format <model> --save` | same: `definition/` gone, `cultures/`, `tables/`, `model.tmdl`, `relationships.tmdl` at the root |

In both cases the model is re-serialized into the flat **root** TMDL layout
(`model.tmdl`, `tables/`, `cultures/`, `functions/` at the `SemanticModel` root)
and **`definition/` is deleted**. `definition.pbism` survives and then points at a
folder that no longer exists — the project will not open.

Safe pattern for on-disk PBIP model edits — **never `--save` against the project**:

```bash
te script <model> -S x.csx --save-to <tempdir> --serialization tmdl
te format <model>      --save-to <tempdir> --serialization tmdl
```

then transplant **only** the changed per-table files from `<tempdir>/tables/*.tmdl`
into the real `definition/tables/`. `te` preserves `///` descriptions and
`lineageTag`s and mints valid GUIDs for new objects.

On a large existing table, insert just the new column blocks into the original
file rather than copying the whole generated file — `te` reformats everything else
(one real case went 195 → 347 lines of diff for a few new columns).

To reformat DAX without touching the folder layout at all, format **one
expression at a time** — `te format -e "<dax>"` prints the formatted text and
writes nothing. `te` formats short-line by default; `--long` is the opt-in.

**Recovery** if `--save` already clobbered it and the model was git-clean:
`git checkout -- "<Model>.SemanticModel"`, then `git clean -fd` the leftovers at
the root (`tables/`, `cultures/`, `*.tmdl`).

## TMDL syntax gotchas

- **`relationships.tmdl` tolerates no comments at all.** A `///` line fails with
  `TmdlSerializationException: Property 'description' is unknown` (a relationship
  has no Description); a `//` line fails with `TmdlFormatException: Unexpected line
  type: Other`. Both blow up when the model is *loaded*, not later in Desktop. Put
  relationship documentation into `///` descriptions on tables and columns, where
  it is accepted, or into markdown beside the model.
- **`formatStringDefinition` must come after `lineageTag`**, otherwise you get an
  indentation parse error.
- **`sortByColumn` must not be cyclic**: a calculated column's sort column cannot
  reference a column whose expression reads the sorted column. Derive order columns
  from the base column instead.
- **Calculated-table columns need an explicit `AddCalculatedTableColumn`** in TE
  scripts — `DATATABLE` columns are not inferred.
- Scaled format strings put the commas before the decimals:
  `#,##0,,.0" M"`.

Validate a model on disk with `te validate -m <Model>.SemanticModel/definition`.
Nothing here validates **DAX** — the Modeling MCP's `dax_query_operations`
Validate is the only tool in this toolkit that does (`modeling-mcp.md`).

## Measure descriptions

A `///` line above a measure becomes its **description**, which Power BI shows as
the tooltip in the Data pane. It has **two parts**: what the measure means, then
the DAX itself after a `---` separator.

```tmdl
	/// Share of completed orders that ended in a complaint: complained / completed. Orders still in progress are left out of the denominator, so the running figure does not drop just because work is unfinished.
	/// 
	/// ---
	/// 
	/// DIVIDE([# complained], [# completed])
	measure 'Complaint rate (%)' = ...
```

The description is written in whatever language the model uses. The same measure
in a Czech-language model, to show that only the prose changes and the two-part
shape does not:

```tmdl
	/// Podíl vyřízených objednávek, které skončily reklamací: reklamované / vyřízené. Rozpracované objednávky se do jmenovatele nepočítají, aby průběžné číslo neklesalo jen kvůli nedokončeným.
	/// 
	/// ---
	/// 
	/// DIVIDE([# reklamovaných], [# vyřízených])
	measure 'Podíl reklamací (%)' = ...
```

**Why the DAX belongs there:** in a **thin report** the model is published, so the
report author cannot see a measure's definition at all — the description is the
only place the formula is visible. Only someone in the original semantic model
gets it for free. That makes the DAX block part of the contract, not padding.

**The prose part:** one sentence saying what the measure answers in business terms,
plus a second **only when there is a real trap** — what is excluded from a
denominator, a sign convention, a currency that gets mixed, a filter the measure
depends on, or a union of sources. Target ≤160 characters **for the prose**; the
DAX block is not counted. Language follows the project (section 6 of its layout
file).

**Keep the DAX block in sync.** It is a copy, so it goes stale when the measure
changes — update it in the same edit, every time. That is the price of the thin
report being able to read it at all.

**Write a description for every measure.** At minimum, none of these may go
without one: anything with a denominator, a sign convention, a filter dependency,
a unioned source, or a configuration/color measure. A config measure says what
changing it affects — e.g. *"Configuration measure — change the hex here and
every conditional format that reads it is recolored."*

### Two anti-patterns, both measured in live models

| Anti-pattern | Why it fails |
|---|---|
| **Restating the DAX in words** — *"This measure is the DISTINCTCOUNT of 'Sales'[OrderId]."* | The formula is already in the `---` block, verbatim. Saying it again in prose spends the useful half of the tooltip on nothing. 79% of one model's descriptions are this shape. |
| **Boilerplate openers** — *"This measure shows…"*, *"Displays…"* | Burns the first words of the tooltip, which is what a reader skimming a field list actually sees. Start with the thing itself. |

For the prose half, the benchmark seen in a production model is **100% coverage at
a median of 103 characters** with neither anti-pattern — prose that good still
needs the `---` blocks added on top.

Run `scripts/check-measure-descriptions.py <repo>` for coverage, missing DAX
blocks and the two anti-patterns.

## M partitions — SQL escaping breaks the whole project

SQL passed to `Value.NativeQuery` lives inside an **M string**, so every quote in
the SQL must be **doubled**:

```m
Query = Value.NativeQuery(Source, "
SELECT z.d AS ""Date"", z.cur AS ""SourceCurrency""
", null, [EnableFolding = false])
```

A single un-doubled quote makes Power BI Desktop refuse to open the **entire
project**:

> There's a problem with the definition content in your Power BI Project.
> M Engine error: 'Microsoft.Data.Mashup.Preview; Token ',' expected.'

This mostly hits PostgreSQL sources, where identifiers must be quoted to keep
their case. MS SQL sidesteps it with `[…]` brackets or plain aliases.

**No standard tool catches this** (verified against a real regression,
2026-08-25):

| Tool | Catches it? |
|---|---|
| `te load` | no — TMDL parses, M is not validated |
| `te format --lang m` | **no** — the formatter is lenient and passes broken input |
| naive quote-balance check | **no** — quotes cancel out in pairs |
| `powerbi-report-author validate` | no — it only inspects the report, not the model |

`te format --lang m` looks like an M validator and is not; it hands out false
greens. The only thing that works is the targeted invariant: in the payload
between `Value.NativeQuery(<Source>, "` and `", null,`, removing every `""` must
leave **zero** quotes. That is what `scripts/check-m-escaping.py` does — run it
after every M partition change.

## DAX

### Filter modifiers over a whole table also clear related dimensions

`ALLEXCEPT(T, …)`, `REMOVEFILTERS(T)` and `ALL(T)` operate on the table's
**expansion** — the table plus every dimension it points to through many-to-one
relationships.

Two real incidents: `ALLEXCEPT` over a web-traffic fact table also cleared `Date`
and the dimension that table points to; `REMOVEFILTERS( Products )` cleared
`'Product groups'[Category]` because `Products` hangs under
`'Product groups'`, so the measure returned the company-wide figure on every row.

**Symptom:** the measure returns the same value on every row, equal to the Total.

**Rule:** remove filters **column by column**, never over a table. And note that
correctness here depends on relationship direction — after any change to a
relationship's direction, re-check the measures that clear filters over that table.

### Currency conversion with an inactive date relationship

Working pattern for: fact table with an **inactive** relationship to `Date`
(needing `USERELATIONSHIP`), `Exchange rates` with an **active** one (cross-filter
risk), rate columns `ExchangeRateDate` / `SourceCurrency` / `TargetCurrency` /
`Rate`.

```dax
Σ Sales =
VAR _currency = [Target currency]
RETURN
IF (
    _currency = "CZK" || _currency = "EUR",
    SUMX (
        ADDCOLUMNS (
            CALCULATETABLE (
                SUMMARIZE (
                    'Sales',
                    'Sales'[AccountingDate],
                    'Sales'[Currency]
                ),
                USERELATIONSHIP ( 'Date'[Date], 'Sales'[AccountingDate] )
            ),
            "@Amount",
                CALCULATE (
                    SUM ( 'Sales'[Amount OC] ),
                    USERELATIONSHIP ( 'Date'[Date], 'Sales'[AccountingDate] )
                ),
            "@Rate",
                COALESCE (
                    LOOKUPVALUE (
                        'Exchange rates'[Rate],
                        'Exchange rates'[ExchangeRateDate], 'Sales'[AccountingDate],
                        'Exchange rates'[SourceCurrency], 'Sales'[Currency],
                        'Exchange rates'[TargetCurrency], _currency
                    ),
                    IF ( _currency = "CZK", 25, 0.04 )
                )
        ),
        [@Amount] * [@Rate]
    ),
    CALCULATE (
        SUM ( 'Sales'[Amount OC] ),
        USERELATIONSHIP ( 'Date'[Date], 'Sales'[AccountingDate] )
    )
)
```

Why it is shaped that way — the things that failed:

- **`TREATAS` + `ALL('Exchange rates')`** is unreliable here; the cross-filter path
  Date → Exchange rates → SourceCurrency interferes with the lookup.
  `LOOKUPVALUE` ignores filter context entirely and matches on the three keys, so
  the whole problem disappears.
- **`SWITCH(…, "OC", …)`** fails when `[Target currency]` returns
  `"(original currency)"` rather than `"OC"` — use `IF(CZK || EUR, …)` with an OC
  fallback.
- **`USERELATIONSHIP` inside `@Amount` alone is not enough** — the `SUMMARIZE` must
  itself be wrapped in `CALCULATETABLE` with `USERELATIONSHIP`.

To adapt it, substitute the fact table, its date column (the one with the inactive
relationship), its source-currency column, the original-currency amount column, and
the fallback rates.

## Relative-date filters follow the report culture, not the model

Power BI's built-in relative-date filtering on **calendar weeks** uses the report
culture's first day of week. A report with `culture: en-US` cuts weeks
Sunday–Saturday even when the model's `Date` table was built with
`firstDayofWeek = Day.Monday` — so the comparison silently shifts by a day and
disagrees with the weekly slicers elsewhere in the report.

**For "previous complete calendar week" on a Monday-first model:** put the
RelativeDate filter on `Date[End of Week]` — "is in the last 7 days", include-today
off, i.e. the window `[today-7 .. today-1]`. `End of Week` is always a Sunday, so
that window contains exactly one: the Sunday that closed the previous week. Works
on any weekday, needs no new measure or column, and inherits the model's
Monday-first weeks. Serialized as `Between` with `DateSpan(DateAdd(Now,-1,Day),
Day)` bounds — the same shape as an MTD filter, with `Amount: -7` and a different
column.

This matters especially on thin reports, which cannot just add a `Week Offset`
column to a published model.

## "Sort by column" needs a functional dependency

Power BI requires name → exactly one sort value. Source `*_Order` columns coming
out of a warehouse routinely violate this — constant values that sort nothing,
duplicates, and `NULL`s all break it.

Before declaring a dimension done, check `count(distinct name)` against
`count(distinct sort)` and look for names carrying more than one order value.
Recompute the ordering (`ROW_NUMBER()` 1..N, grouped ordering derived from
`MIN(child_order)`) with a deterministic tie-break on the business key.

Related: dimension views should carry a default row (key `-1`, `(unknown)` in the
hierarchy columns), with unmatched fact keys mapped to `-1` — otherwise rows with
keys missing from the dimension silently disappear in Power BI or land in a blank
group.
